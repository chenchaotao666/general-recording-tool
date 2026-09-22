<script>
export default {
  onLaunch: function () {
    // 未登录先跳登录页（登录页 reLaunch 回数据表）
    if (!uni.getStorageSync('grt_token')) {
      uni.reLaunch({ url: '/pages/login/index' })
    }
  },
}
</script>

<style>
/*每个页面公共css */
</style>
