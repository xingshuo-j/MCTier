#!/usr/bin/env python3
"""复现尝试 v6: ghost pad bin 转发 + 源任务线程并发 set_caps
结构: audiotestsrc ! [bin(queue ! identity)] ! fakesink
- audiotestsrc 任务线程: 循环切换 caps → gst_base_src_set_caps → push CAPS (Thread A 路径)
- 主线程: 往 ghost pad 上游注入自定义事件 → 事件在 bin 边界走
  gst_pad_event_default → forward (Thread B 路径), 方向与 A 交叉
"""
import gi, threading, time
gi.require_version('Gst', '1.0')
from gi.repository import Gst
Gst.init(None)

src = Gst.ElementFactory.make('audiotestsrc', 'src')
src.set_property('num-buffers', -1)

# 内部 bin: queue ! identity, 有 ghost pad (事件转发会触发 event_default/forward)
bin_ = Gst.Bin.new('filter-bin')
q = Gst.ElementFactory.make('queue', 'q')
ident = Gst.ElementFactory.make('identity', 'ident')
bin_.add(q); bin_.add(ident); q.link(ident)
# ghost pad: bin 的 src/sink
sink_ghost = Gst.GhostPad.new('sink', q.get_static_pad('sink'))
src_ghost = Gst.GhostPad.new('src', ident.get_static_pad('src'))
bin_.add_pad(sink_ghost); bin_.add_pad(src_ghost)

fsink = Gst.ElementFactory.make('fakesink', 'fsink')
fsink.set_property('sync', False)

pipeline = Gst.Pipeline.new('t6')
for e in (src, bin_, fsink):
    pipeline.add(e)
src.link(bin_); bin_.link(fsink)

stop = threading.Event()

def src_flip():
    """模拟源任务线程协商: 改 caps 强制 set_caps→push CAPS"""
    fmts = ['S16LE','S24LE','S32LE','F32LE']
    i = 0
    while not stop.is_set():
        # 直接改 src 的 caps 属性? audiotestsrc 无 caps 属性, 用 capsfilter 前面
        f = fmts[i % len(fmts)]
        rate = 48000 + (i % 8) * 1000
        # 通过 src 的 srcpad 推 CAPS (模拟 set_caps 后的事件)
        cap = Gst.Caps.from_string(f'audio/x-raw,format=(string){f},rate=(int){rate},channels=(int)2')
        spad = src.get_static_pad('src')
        spad.push_event(Gst.Event.new_caps(cap))
        i += 1
    print(f'[A-src] 推 {i} 次')

def bin_inject():
    """从 bin 的 src ghost pad 注入事件 → 反向穿越触发转发"""
    # 注: 从 ghost src pad 推下游事件会进入 fakesink
    # 从 sink ghost pad 推事件会进 queue 再往 src 反向
    caps2 = Gst.Caps.from_string('audio/x-raw,format=(string)F64LE,rate=(int)96000,channels=(int)1')
    i = 0
    while not stop.is_set():
        # 往 sink_ghost(即 queue 的 sink, 连接 src 的 src pad) 推 CAPS
        # 但 sink pad 推 CAPS 是错误方向... 改推 CUSTOM_DOWNSTREAM
        ev = Gst.Event.new_custom(Gst.EventType.CUSTOM_DOWNSTREAM, Gst.Structure.new_empty('x-test'))
        sink_ghost.push_event(ev)  # 下游方向, 会触发 queue/bin 的事件转发
        i += 1
    print(f'[B-inject] 推 {i} 次')

print('启动...')
pipeline.set_state(Gst.State.PLAYING)
time.sleep(1.0)

t1 = threading.Thread(target=src_flip, daemon=True)
t2 = threading.Thread(target=bin_inject, daemon=True)
t1.start(); t2.start()

for i in range(20):
    time.sleep(1)
    if i % 5 == 4:
        print(f'  {i+1}s (A={t1.is_alive()}, B={t2.is_alive()})')
print('停止...')
stop.set(); time.sleep(2)
a,b = t1.is_alive(), t2.is_alive()
pipeline.set_state(Gst.State.NULL)
print(f'A={a}, B={b}')
print('⚠️ 疑似死锁' if (a or b) else '✅ 无死锁')
