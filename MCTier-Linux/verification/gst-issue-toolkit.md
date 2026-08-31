# GStreamer issue 工具包（原样贴出，无 AI 叙述）

## 1. 复现环境与命令（工具输出）

```
OS: Debian 13 (trixie), x86_64
GStreamer: 1.26.2-2 (Debian, 含 libgstreamer1.0-0-dbgsym)
WebKitGTK: 2.52.6 (自建 ENABLE_WEB_RTC=ON, 含对应 dbgsym)
触发: WebKitGTK WebRTC 应用中, getUserMedia({audio}) 成功后,
     对 PLAYING 状态的 RTCPeerConnection 调用 addTrack() 触发重协商,
     100% 复现（音频采集/播放线程存活, 仅事件面死锁, 整个 WebProcess 卡死）

抓栈命令:
gdb -p <WebProcess PID> -batch \
  -ex "set debug-file-directory /usr/lib/debug" \
  -ex "thread apply all bt"
```

## 2. 符号化双线程栈（gdb 输出，gst-deadlock-symbolized-threads.txt 全文）

```
（见 gst-deadlock-symbolized-threads.txt，两段：#0 futex_wait 双栈）
```

## 3. 关键帧摘要（截取自上面的 gdb 输出）

```
Thread A（等 pad B 锁, 持 pad A 锁）:
#4 gst_pad_send_event_unchecked (pad=0x…4ad370) gstpad.c:5972   ← futex_wait 目标
#5 gst_pad_push_event_unchecked (pad=0x…4ac3a0) gstpad.c:5666
#6 push_sticky (pad=0x…4ac3a0) gstpad.c:4104
#7 events_foreach (pad=0x…4ac3a0) gstpad.c:622                   ← 持 pad A 对象锁
#8 check_sticky (pad=0x…4ac3a0) gstpad.c:4164
#9 gst_pad_push_event (pad=0x…4ac3a0) gstpad.c:5806
#19 gst_task_func gsttask.c:399                                  ← 来自 WebKit 流任务线程

Thread B（等 downstream 锁, 持 pad B 链上的锁）:
#4 gst_pad_send_event_unchecked (pad=0x…ced7cb00) gstpad.c:5972   ← futex_wait 目标
… gst_pad_event_default → gst_pad_forward → event_forward_func …（转发链重入相邻 pad）
```

## 4. 附加对照实验（工具输出）

```
对最外层 gst_pad_push_event 加线程感知全局互斥后重抓（same repro）:
死锁从 "pad A 锁 vs pad B 锁" 变为 "全局锁 vs pad A 对象锁"
→ 锁序反转是结构性的: 相邻 pad 上并发 downstream 事件推送无法与
  check_sticky/push_sticky 的每-pad 对象锁顺序共存
（对照栈见 deadlock-with-global-serialization-patch.txt）
```
