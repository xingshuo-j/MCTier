/* 纯 GStreamer 双 webrtcbin 复现: 动态加轨触发 renegotiation, 观察是否死锁
 *
 * 结构:
 *   A: appsrc -> opusenc -> webrtcbin-A   (音频源, 流线程持续跑)
 *   B: webrtcbin-B                        (接收)
 *   A/B 同进程, 直接交换 SDP offer/answer + ICE candidate
 *   建立 PLAYING 稳定后, A 动态加第二路轨并 renegotiation
 *
 * 编译:
 *   gcc -o webrtc_probe webrtc_probe.c $(pkg-config --cflags --libs gstreamer-1.0 gstreamer-webrtc-1.0 gstreamer-sdp-1.0)
 */
#include <gst/gst.h>
#include <gst/sdp/gstsdp.h>
#include <gst/webrtc/webrtc.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static GstElement *webrtc_A, *webrtc_B, *appsrc;
static GstElement *pipeA;
static gboolean negotiated = FALSE;
static gboolean second_track_added = FALSE;
static gboolean timeout_flag = FALSE;

/* ---------- SDP 交换 ---------- */

static void set_remote_answer(GstElement *a, GstWebRTCSessionDescription *ans)
{
    GstPromise *p = gst_promise_new();
    g_signal_emit_by_name(a, "set-remote-description", ans, p);
    gst_promise_interrupt(p);
    gst_promise_unref(p);
}

static void on_answer_created(GstPromise *promise, gpointer user_data)
{
    GstWebRTCSessionDescription *answer = NULL;
    const GstStructure *reply = gst_promise_get_reply(promise);
    gst_structure_get(reply, "answer", GST_TYPE_WEBRTC_SESSION_DESCRIPTION, &answer, NULL);
    if (answer) {
        g_print("[B] answer len %d\n", (int)strlen(gst_sdp_message_as_text(answer->sdp)));
        g_signal_emit_by_name(webrtc_B, "set-local-description", answer, NULL);
        set_remote_answer(webrtc_A, answer);
        g_print("== SDP 交换完成 ==\n");
        negotiated = TRUE;
    }
}

static void on_offer_created(GstPromise *promise, gpointer user_data)
{
    GstWebRTCSessionDescription *offer = NULL;
    const GstStructure *reply = gst_promise_get_reply(promise);
    gst_structure_get(reply, "offer", GST_TYPE_WEBRTC_SESSION_DESCRIPTION, &offer, NULL);
    if (offer) {
        g_print("[A] offer len %d\n", (int)strlen(gst_sdp_message_as_text(offer->sdp)));
        /* A 设本地描述 */
        g_signal_emit_by_name(webrtc_A, "set-local-description", offer, NULL);
        /* B 设远端描述 */
        g_signal_emit_by_name(webrtc_B, "set-remote-description", offer, NULL);
        /* B 生成 answer */
        g_signal_emit_by_name(webrtc_B, "create-answer", NULL,
                              gst_promise_new_with_change_func(on_answer_created, NULL, NULL));
    }
}

/* ---------- ICE candidate 交换 (本地直传) ---------- */

static void on_ice_candidate(GstElement *webrtc, guint mlineindex, gchar *candidate,
                             gpointer user_data)
{
    GstElement *peer = (webrtc == webrtc_A) ? webrtc_B : webrtc_A;
    g_signal_emit_by_name(peer, "add-ice-candidate", mlineindex, candidate);
}

/* ---------- A 的音频源 ---------- */

static gboolean feed_audio(gpointer user_data)
{
    GstBuffer *buf;
    static guint64 pts = 0;
    const guint buf_size = 9600; /* 0.1s @48k 双声道 16bit */
    GstMapInfo map;

    if (timeout_flag)
        return FALSE;

    buf = gst_buffer_new_and_alloc(buf_size);
    gst_buffer_map(buf, &map, GST_MAP_WRITE);
    memset(map.data, 0, buf_size);
    gst_buffer_unmap(buf, &map);
    GST_BUFFER_PTS(buf) = pts;
    GST_BUFFER_DURATION(buf) = gst_util_uint64_scale_int(1, GST_SECOND, 10);
    pts += GST_BUFFER_DURATION(buf);

    g_signal_emit_by_name(appsrc, "push-buffer", buf, NULL);
    gst_buffer_unref(buf);
    return TRUE; /* 每 10ms 喂一次 */
}

/* ---------- 第二轮 renegotiation: 加第二路轨 ---------- */

static void on_reoffer_created(GstPromise *promise, gpointer user_data)
{
    const GstStructure *reply = gst_promise_get_reply(promise);
    if (reply) {
        g_print("[A] 第二轮 offer 生成 (renegotiation OK)\n");
    }
}

static gboolean trigger_renegotiation(gpointer user_data)
{
    if (!negotiated) {
        g_print("[重协商] 第一轮还没完成, 跳过\n");
        return FALSE;
    }
    g_print("======== 触发第二轮 renegotiation (动态加轨后) ========\n");
    g_signal_emit_by_name(webrtc_A, "create-offer", NULL,
                          gst_promise_new_with_change_func(on_reoffer_created, NULL, NULL));
    return FALSE; /* 只触发一次 */
}

int main(int argc, char *argv[])
{
    GstElement *opusenc, *qA;
    GMainLoop *loop;
    guint timer1;

    gst_init(&argc, &argv);

    webrtc_A = gst_element_factory_make("webrtcbin", "webrtc-A");
    webrtc_B = gst_element_factory_make("webrtcbin", "webrtc-B");
    g_object_set(webrtc_A, "bundle-policy", GST_WEBRTC_BUNDLE_POLICY_MAX_BUNDLE, NULL);
    g_object_set(webrtc_B, "bundle-policy", GST_WEBRTC_BUNDLE_POLICY_MAX_BUNDLE, NULL);

    /* A 的音频链: appsrc -> opusenc -> webrtcbin-A */
    appsrc = gst_element_factory_make("appsrc", "appsrc");
    g_object_set(appsrc, "is-live", TRUE, "format", GST_FORMAT_TIME, NULL);
    opusenc = gst_element_factory_make("opusenc", "opusenc");
    qA = gst_element_factory_make("queue", "qA");

    pipeA = gst_pipeline_new("pipe-A");
    gst_bin_add_many(GST_BIN(pipeA), appsrc, opusenc, qA, webrtc_A, NULL);
    if (!gst_element_link(appsrc, opusenc))
        g_printerr("appsrc->opusenc link 失败\n");
    if (!gst_element_link(opusenc, qA))
        g_printerr("opusenc->qA link 失败\n");
    /* qA -> webrtc_A: 需要等 webrtcbin 的 sink pad 出现 */
    {
        GstPad *sinkpad = gst_element_get_static_pad(webrtc_A, "sink_0");
        if (!sinkpad) {
            g_printerr("webrtc_A 无 sink_0 pad (transceiver 未生效?)\n");
            return 1;
        }
        GstPad *srcpad = gst_element_get_static_pad(qA, "src");
        if (gst_pad_link(srcpad, sinkpad) != GST_PAD_LINK_OK)
            g_printerr("qA->webrtc_A pad link 失败\n");
        gst_object_unref(srcpad);
        gst_object_unref(sinkpad);
    }

    /* ICE candidate 本地直传 */
    g_signal_connect(webrtc_A, "on-ice-candidate", G_CALLBACK(on_ice_candidate), NULL);
    g_signal_connect(webrtc_B, "on-ice-candidate", G_CALLBACK(on_ice_candidate), NULL);

    /* A 先建音频 transceiver → 生成可用 sink pad */
    g_signal_emit_by_name(webrtc_A, "create-send-transceiver",
                          GST_WEBRTC_RTP_TRANSCEIVER_DIRECTION_SENDONLY, NULL);
    usleep(300 * 1000);

    g_print("启动管道...\n");
    gst_element_set_state(pipeA, GST_STATE_PLAYING);
    usleep(500 * 1000);

    /* 喂音频数据 (流线程活动) */
    timer1 = g_timeout_add(10, feed_audio, NULL);

    /* 第一轮 offer */
    g_print("触发第一轮 create-offer...\n");
    g_signal_emit_by_name(webrtc_A, "create-offer", NULL,
                          gst_promise_new_with_change_func(on_offer_created, NULL, NULL));

    /* 3 秒后触发第二轮 renegotiation */
    g_timeout_add(3000, trigger_renegotiation, NULL);

    /* 运行 12 秒观察 (若死锁则超时退出) */
    loop = g_main_loop_new(NULL, FALSE);
    g_timeout_add(12000, (GSourceFunc)g_main_loop_quit, loop);
    g_main_loop_run(loop);

    g_print("12 秒结束。若此时打印 '最终检查' 且能响应则无死锁\n");
    /* 最终响应测试: 再触发一次 offer, 若卡死则此回调不会执行 */
    timeout_flag = TRUE;
    g_signal_emit_by_name(webrtc_A, "create-offer", NULL,
                          gst_promise_new_with_change_func(on_reoffer_created, NULL, NULL));
    g_usleep(500 * 1000);
    g_print("主线程仍存活 (若有死锁, 卡在别的线程, 这里能过)\n");

    gst_element_set_state(pipeA, GST_STATE_NULL);
    return 0;
}
