from src.extract import ts_extractor as ts


def test_extract_imports_named_and_default():
    text = """
import { useState, useEffect } from 'react';
import axios from 'axios';
import { api } from '~/api/client';
"""
    imports = ts.extract_imports(text)
    sources = {i.source for i in imports}
    assert "react" in sources
    assert "axios" in sources
    internal = [i for i in imports if i.is_internal]
    assert len(internal) == 1
    assert internal[0].source == "~/api/client"


def test_extract_interfaces_with_fields():
    text = """
export interface AlumniDraft {
  fullName: string;
  yearOfPassing: number | null;
}
"""
    models = ts.extract_interfaces(text)
    assert len(models) == 1
    assert models[0].name == "AlumniDraft"
    field_names = {f.name for f in models[0].fields}
    assert field_names == {"fullName", "yearOfPassing"}


def test_extract_functions_exported_and_unexported():
    text = """
export async function fetchThing(): Promise<void> {
  return;
}

function helper(): number {
  return 1;
}
"""
    functions = ts.extract_functions(text)
    names = {f.name for f in functions}
    assert names == {"fetchThing", "helper"}


def test_extract_functions_arrow_const_with_hook_wrapper():
    text = """
const refresh = useCallback(
  (message: string) => {
    doSomething(message);
  },
  [dep],
);
"""
    functions = ts.extract_functions(text)
    assert len(functions) == 1
    assert functions[0].name == "refresh"


def test_extract_api_calls_literal_and_template():
    text = """
await api.get('/alumni');
await api.put(`/alumni/${id}`, draft);
"""
    calls = ts.extract_api_calls(text)
    assert len(calls) == 2
    get_call = next(c for c in calls if c.method == "GET")
    assert get_call.url == "/alumni"
    assert get_call.url_is_template is False
    put_call = next(c for c in calls if c.method == "PUT")
    assert put_call.url_is_template is True


def test_extract_event_handlers_named_and_inline():
    text = """
function handleClick() {
  doThing();
}

const el = <Button onClick={() => setOpen(true)}>Go</Button>;
"""
    functions = ts.extract_functions(text)
    handlers = ts.extract_event_handlers(text, functions)
    named = [h for h in handlers if not h.assumed]
    inline = [h for h in handlers if h.assumed]
    assert len(named) == 1
    assert named[0].name == "handleClick"
    assert len(inline) == 1
    assert inline[0].event_type == "user_action"


def test_find_props_interface():
    text = """
export interface ButtonProps {
  label: string;
}
"""
    models = ts.extract_interfaces(text)
    found = ts.find_props_interface("Button", models)
    assert found is not None
    assert found.name == "ButtonProps"
    assert ts.find_props_interface("Other", models) is None


def test_extract_base_url():
    text = "export const api = axios.create({ baseURL: '/api/v1', timeout: 1000 });"
    assert ts.extract_base_url(text) == "/api/v1"
