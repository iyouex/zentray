<template>
  <div class="page">
    <div class="page-header">
      <h2>ZenTray</h2>
      <a-tag color="arcoblue">Vue + Arco</a-tag>
    </div>
    <a-result
      status="info"
      title="前端已就绪"
      subtitle="请从系统托盘菜单打开具体功能页。开发调试可直接访问下列路由。"
    >
      <template #extra>
        <a-space wrap>
          <a-button type="primary" @click="$router.push('/tasks')">任务列表</a-button>
          <a-button @click="$router.push('/tasks/new')">新建任务</a-button>
          <a-button @click="$router.push('/settings')">设置</a-button>
        </a-space>
      </template>
    </a-result>
  </div>
</template>
