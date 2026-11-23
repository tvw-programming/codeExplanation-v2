"""Vue / Solid / Qwik honesty enrichments (EXTRACTOR_VERSION 22)."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract.qwik import extract as qwik_extract
from src.extract.qwik.record import build_qwik_chunk_record
from src.extract.solid import extract as solid_extract
from src.extract.solid.record import build_solid_chunk_record
from src.extract.vue import extract as vue_extract
from src.extract.vue.record import build_vue_chunk_record
from src.storage.mirror_store import EXTRACTOR_VERSION

FIX = Path(__file__).resolve().parent / "fixtures"


def test_extractor_version_22():
    assert EXTRACTOR_VERSION == 23


def test_vue_template_line_and_props_and_script_setup_signals():
    text = """<script setup>
const name = ref('x')
const full = computed(() => name.value)
onMounted(() => {})
</script>
<template>
  <Avatar :src="url" alt="a" />
  <button @click="onSave">Save</button>
</template>
"""
    sfc = vue_extract.extract_vue_sfc(text, file_stem="UserCard")
    assert sfc.script_setup is True
    assert len(sfc.components) == 1
    avatar = sfc.components[0]
    assert avatar["child"] == "Avatar"
    assert avatar["assumed"] is False
    # Line is in the full file, not template-local offset 0.
    assert avatar["line"] >= 6
    prop_names = {p["name"] for p in avatar["props"]}
    assert "src" in prop_names
    assert "alt" in prop_names
    kinds = {s["kind"] for s in sfc.signals}
    assert "ref" in kinds and "computed" in kinds
    assert all(s["owner"] == "UserCard" and s["assumed"] is False for s in sfc.signals)
    assert any(e["kind"] == "onMounted" and e["assumed"] is False for e in sfc.effects)


def test_vue_skips_dynamic_is_component():
    text = """<template>
  <component :is=" whichev " />
  <Widget :is="dyn" />
  <StaticChild />
</template>
"""
    sfc = vue_extract.extract_vue_sfc(text, file_stem="Dyn")
    children = {c["child"] for c in sfc.components}
    assert "StaticChild" in children
    assert "Widget" not in children
    assert "component" not in {c["child"].lower() for c in sfc.components}


def test_vue_fixture_record_mount_line():
    src = (FIX / "vue" / "UserCard.vue").read_text()
    # Write via tmp through record builder path
    root = FIX / "vue"
    rec = build_vue_chunk_record(
        root,
        ChunkPlan("UserCard", "UI", "vue", "UserCard.vue", 20, "small"),
        {"frontend": "vue", "backend": []},
    )
    assert rec["extractorVersion"] == 23
    mounts = rec["jsxMounts"]
    assert any(m["child"] == "Avatar" and m["line"] >= 6 for m in mounts)
    assert rec["vueMeta"]["scriptSetup"] is True
    assert rec["vueMeta"]["hasProps"] is True


def test_solid_signal_owner_innermost_function():
    text = """
export function Counter() {
  const [count, setCount] = createSignal(0);
  return <Button onClick={() => setCount(1)} />;
}
function helper() {
  createMemo(() => 1);
}
createSignal(0);
"""
    facts = solid_extract.extract_solid(text, "File")
    by_line = {s["line"]: s for s in facts.signals}
    counter_sig = next(s for s in facts.signals if s["kind"] == "createSignal" and s["owner"] == "Counter")
    assert counter_sig["assumed"] is False
    memo = next(s for s in facts.signals if s["kind"] == "createMemo")
    assert memo["owner"] == "helper" and memo["assumed"] is False
    orphan = next(s for s in facts.signals if s["owner"] == "File")
    assert orphan["assumed"] is True
    assert any(m["parent"] == "Counter" and m["child"] == "Button" for m in facts.mounts)


def test_solid_fixture_record_owner():
    root = FIX / "solid"
    rec = build_solid_chunk_record(
        root,
        ChunkPlan("Counter", "UI", "solid", "Counter.tsx", 20, "small"),
        {"frontend": "solid", "backend": []},
    )
    assert rec["signals"]
    assert rec["signals"][0]["owner"] == "Counter"
    assert rec["signals"][0]["assumed"] is False
    graph = rec["visualGraph"]
    assert graph is not None
    owns = [e for e in graph["edges"] if e["kind"] == "owns_state"]
    assert owns and owns[0]["assumed"] is False


def test_qwik_component_dollar_bind_name_and_signal_owner():
    text = """
import { component$, useSignal } from '@builder.io/qwik';

export const Greeter = component$(() => {
  const name = useSignal('world');
  return (
    <div>
      <Badge label={name.value} />
      <button onClick$={() => { name.value = 'Qwik'; }}>Hi</button>
    </div>
  );
});
"""
    facts = qwik_extract.extract_qwik(text, "Greeter")
    comp = next(b for b in facts.boundaries if b["kind"] == "component$")
    assert comp["name"] == "Greeter"
    assert comp["assumed"] is False
    assert facts.signals
    assert facts.signals[0]["owner"] == "Greeter"
    assert facts.signals[0]["assumed"] is False
    assert any(m["parent"] == "Greeter" and m["child"] == "Badge" for m in facts.mounts)
    assert any(b["kind"] == "handler$" and b["name"] == "onClick" for b in facts.boundaries)


def test_qwik_unbound_component_dollar_assumed():
    text = "component$(() => { return null; });\n"
    facts = qwik_extract.extract_qwik(text, "Orphan")
    comps = [b for b in facts.boundaries if b["kind"] == "component$"]
    assert comps and comps[0].get("assumed") is True
    assert "name" not in comps[0]


def test_qwik_fixture_record():
    root = FIX / "qwik"
    rec = build_qwik_chunk_record(
        root,
        ChunkPlan("Greeter", "UI", "qwik", "Greeter.tsx", 20, "small"),
        {"frontend": "qwik", "backend": []},
    )
    assert any(b.get("name") == "Greeter" for b in rec["qwikBoundaries"])
    assert rec["signals"][0]["owner"] == "Greeter"
    assert rec["signals"][0]["assumed"] is False
