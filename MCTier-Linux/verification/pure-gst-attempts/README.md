# 纯 GStreamer 复现尝试记录 (2026-09-02)

目标: 复现 WebKitGTK 场景的 sticky-event ABBA 死锁, 不依赖 WebKit。

## 尝试过的构造 (全部未在测试窗口内死锁)

1. `gst_deadlock_probe.py` — fakesrc!queue!fakesink, 两线程对同一对 pad 相反方向推 CAPS
   → 未死锁 (往 sink pad 推下游 CAPS 是错误方向, 被 GStreamer 拒绝, 线程空转)
2. `gst_deadlock_probe2.py` — 双 fakesrc 共享 tee, 两线程各推 CAPS
   → 未死锁 (CAPS 不变时 sticky 重推被短路)
3. `gst_deadlock_probe3.py` — fakesrc 无 caps 属性, 报错弃用
4. `gst_deadlock_probe4.py` — 双 audiotestsrc + capsfilter 反复切格式 + 共享 tee
   → 未死锁 (各切 300-400 万次格式, 任务线程反复协商, 正常退出)
5. `gst_deadlock_probe5.py` — 反复 link/unlink tee 分支 + 持续推事件
   → 未死锁 (有分支泄漏, 不干净)
6. `gst_deadlock_probe6.py` — audiotestsrc + ghost-pad bin + 双线程
   → 未死锁
7. `webrtc_probe.c` — 双 webrtcbin 互联 + 动态加轨 renegotiation
   → 卡在 webrtcbin 的 transceiver/sink-pad 时序, 未能跑到 renegotiation 场景 (放弃)

## 结论

简单构造无法触发; 竞态窗口依赖 WebKit 特定并发时序
(源 streaming task 协商 caps 的同时, 另一线程在同一 pad graph 上转发事件)。
纯 GStreamer 复现不可行, WebKit 场景作为参考复现保留。

## 相关证据文件

- `../gst-deadlock-symbolized-threads.txt` — 符号化双死锁线程栈
- `../deadlock-with-global-serialization-patch.txt` — 全局互斥对照实验栈
