#!/usr/bin/env python3
"""复现尝试 v2: 两个源同时推事件, 交叉经过共享 tee
结构: fakesrc1 ! queue1 ! tee ! queue_sink ! fakesink
      fakesrc2 ! queue2 ! tee (第二个输入)
线程A: 从 src1 推 CAPS (下游方向, 持 src1/queue1 链上锁)
线程B: 从 src2 推 CAPS (交叉方向, 经 tee 转发)
tee 的 src pad 被两个线程共享 → 反向锁序窗口
"""
import gi, threading, time
gi.require_version('Gst', '1.0')
from gi.repository import Gst

Gst.init(None)

src1 = Gst.ElementFactory.make('fakesrc', 'src1')
src1.set_property('is-live', True)
src2 = Gst.ElementFactory.make('fakesrc', 'src2')
src2.set_property('is-live', True)
q1 = Gst.ElementFactory.make('queue', 'q1')
q2 = Gst.ElementFactory.make('queue', 'q2')
tee = Gst.ElementFactory.make('tee', 'tee')
qs = Gst.ElementFactory.make('queue', 'qs')
sink = Gst.ElementFactory.make('fakesink', 'sink')
sink.set_property('sync', False)

pipeline = Gst.Pipeline.new('t2')
for e in (src1, src2, q1, q2, tee, qs, sink):
    pipeline.add(e)
src1.link(q1); src2.link(q2)
q1.link(tee); q2.link(tee)
tee.link(qs); qs.link(sink)

# 两个 tee 输入: q1 连 tee 的 sink_0, q2 连 tee 的 sink_1
sink1 = tee.get_static_pad('sink_0') or tee.request_pad_simple('sink_%u')
sink2 = tee.get_static_pad('sink_1') or tee.request_pad_simple('sink_%u')

stop = threading.Event()

def push_loop(pad, name, fmt):
    caps = Gst.Caps.from_string(f'audio/x-raw,format=(string){fmt},rate=(int)48000,channels=(int)2')
    i = 0
    while not stop.is_set():
        pad.push_event(Gst.Event.new_caps(caps))
        i += 1
    print(f'[{name}] 推 {i} 事件')

print('启动管道...')
pipeline.set_state(Gst.State.PLAYING)
time.sleep(1.0)

t1 = threading.Thread(target=push_loop, args=(src1.get_static_pad('src'), 'A-src1', 'S16LE'), daemon=True)
t2 = threading.Thread(target=push_loop, args=(src2.get_static_pad('src'), 'B-src2', 'F32LE'), daemon=True)
t1.start(); t2.start()

print('压力测试 20 秒...')
for i in range(20):
    time.sleep(1)
    if i % 5 == 4:
        print(f'  {i+1}s')

print('停止...')
stop.set(); time.sleep(1.5)
a, b = t1.is_alive(), t2.is_alive()
pipeline.set_state(Gst.State.NULL)
print(f'A alive={a}, B alive={b}')
print('⚠️ 疑似死锁' if (a or b) else '✅ 无死锁')
