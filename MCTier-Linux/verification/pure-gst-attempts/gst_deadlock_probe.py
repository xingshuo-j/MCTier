#!/usr/bin/env python3
"""纯 GStreamer ABBA 死锁复现尝试
构造: fakesrc ! queue ! fakesink
线程1: 循环从 src pad 推 CAPS (下游方向, 持上游pad锁 → 推下游pad)
线程2: 循环往 sink pad 注入事件 (触发向下游/上游转发)
"""
import gi, threading, time, sys, signal
gi.require_version('Gst', '1.0')
from gi.repository import Gst

Gst.init(None)

# 管道: fakesrc(num_buffers=0 无限流) ! queue ! fakesink
src = Gst.ElementFactory.make('fakesrc', 'src')
src.set_property('num-buffers', 0)
src.set_property('is-live', True)  # 让 src 跑任务线程持续发数据
queue = Gst.ElementFactory.make('queue', 'queue')
sink = Gst.ElementFactory.make('fakesink', 'sink')
sink.set_property('sync', False)

pipeline = Gst.Pipeline.new('test')
pipeline.add(src); pipeline.add(queue); pipeline.add(sink)
src.link(queue); queue.link(sink)

srcpad = src.get_static_pad('src')
sinkpad = queue.get_static_pad('sink')  # 连接 src 的下游

stop = threading.Event()
deadlock_detected = threading.Event()

def thread_downstream():
    """从 src pad 推下游 CAPS 事件 (模拟 base_src 协商推 caps)"""
    caps = Gst.Caps.from_string('audio/x-raw,format=(string)S16LE,rate=(int)48000,channels=(int)2')
    i = 0
    while not stop.is_set():
        ev = Gst.Event.new_caps(caps)
        srcpad.push_event(ev)
        i += 1
    print(f'[下游线程] 共推 {i} 个事件')

def thread_upstream():
    """往 queue 的 sink pad 推事件 (触发向下游方向但来自另一线程的 sticky 重推)"""
    caps2 = Gst.Caps.from_string('audio/x-raw,format=(string)F32LE,rate=(int)44100,channels=(int)1')
    i = 0
    while not stop.is_set():
        ev = Gst.Event.new_caps(caps2)
        sinkpad.push_event(ev)
        i += 1
    print(f'[注入线程] 共推 {i} 个事件')

print('启动管道...')
pipeline.set_state(Gst.State.PLAYING)
time.sleep(0.5)

t1 = threading.Thread(target=thread_downstream, daemon=True)
t2 = threading.Thread(target=thread_upstream, daemon=True)
t1.start(); t2.start()

# 观察 15 秒: 主线程每 2 秒检查是否卡死(通过心跳计数)
print('开始 15 秒压力测试...')
for i in range(15):
    time.sleep(1)
    if i % 5 == 4:
        print(f'  ...{i+1}s 仍在运行')

print('停止测试...')
stop.set()
time.sleep(1)
print('设置 STOPPED, 检查线程是否卡住...')
t1_alive = t1.is_alive()
t2_alive = t2.is_alive()
print(f'下游线程 alive={t1_alive}, 注入线程 alive={t2_alive}')

pipeline.set_state(Gst.State.NULL)
if t1_alive or t2_alive:
    print('⚠️ 线程未退出 — 可能发生了死锁')
else:
    print('✅ 无死锁, 线程正常退出')
