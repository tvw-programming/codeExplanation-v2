<script setup>
import Avatar from './Avatar.vue'
const props = defineProps({ name: String })
const emit = defineEmits(['save'])
function onSave() { emit('save') }
</script>
<template>
  <Avatar />
  <button @click="onSave">Save</button>
</template>
