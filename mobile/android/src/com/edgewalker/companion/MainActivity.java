/* SPDX-License-Identifier: Apache-2.0 */
package com.edgewalker.companion;

import android.app.Activity;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.InputFilter;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/** A foreground-only console for a local simulator or a read-only serial gateway. */
public final class MainActivity extends Activity {
    private static final int INK = Color.rgb(26, 45, 48);
    private static final int MUTED = Color.rgb(100, 118, 117);
    private static final int TEAL = Color.rgb(17, 121, 107);
    private static final int PALE = Color.rgb(230, 242, 237);
    private static final int ORANGE = Color.rgb(166, 92, 28);
    private static final int RED = Color.rgb(173, 49, 49);
    private static final int BG = Color.rgb(243, 245, 242);
    private static final int MAX_LOG_LINES = 36;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Set<String> capabilities = new HashSet<>();
    private final Map<String, Pending> pending = new HashMap<>();
    private final ArrayList<String> logLines = new ArrayList<>();
    private final String sessionId = UUID.randomUUID().toString().substring(0, 8);
    private long requestSequence;
    private int connectionGeneration;
    private boolean destroyed;
    private boolean connecting;
    private boolean ready;
    private boolean subscribed;
    private boolean prototypeFixture;
    private long lastStateElapsed;
    private long lastAppliedStateSequence = Long.MIN_VALUE;
    private long lastEventId = Long.MIN_VALUE;
    private String activeOrigin = "";
    private String lastStateOrigin = "";
    private String profile = "";
    private String lastStateDescription = "尚未收到状态";
    private JsonLineClient client;

    private EditText hostInput;
    private EditText portInput;
    private EditText pairInput;
    private EditText questionInput;
    private Button connectButton;
    private Button disconnectButton;
    private Button refreshButton;
    private Button softButton;
    private Button strongButton;
    private Button walkButton;
    private Button cycleButton;
    private Button askButton;
    private TextView connectionText;
    private TextView sourceText;
    private TextView connectionDetail;
    private TextView rangeValue;
    private TextView speedValue;
    private TextView levelValue;
    private TextView radarText;
    private TextView updatedText;
    private TextView profileText;
    private TextView actionText;
    private TextView replyText;
    private TextView eventsText;
    private TextView capabilitiesText;
    private TextView noticeTitle;
    private TextView noticeBody;
    private TextView connectionTitle;
    private TextView connectionSubtitle;
    private TextView stateSubtitle;
    private TextView controlSubtitle;
    private TextView askSubtitle;

    private static final class Pending {
        final String operation;
        final RequestWaitState waitState;

        Pending(String operation) {
            this.operation = operation;
            this.waitState = new RequestWaitState(operation, SystemClock.elapsedRealtime());
        }
    }

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        buildScreen();
        SharedPreferences preferences = getPreferences(MODE_PRIVATE);
        hostInput.setText(preferences.getString("host", "10.0.2.2"));
        portInput.setText(preferences.getString("port", "8765"));
        if (savedInstanceState != null) {
            questionInput.setText(savedInstanceState.getString("question", ""));
        }
        updateControls();
        appendLog("控制台就绪；点击连接后才会访问填写的地址");
        main.postDelayed(watchdog, 1000);
    }

    private void buildScreen() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BG);
        scroll.setClipToPadding(false);
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(22), dp(26), dp(22), dp(28));
        scroll.addView(page, new ScrollView.LayoutParams(-1, -2));
        setContentView(scroll);

        // Android 15 enforces edge-to-edge for target 35; keep controls outside bars/IME.
        scroll.setOnApplyWindowInsetsListener((view, insets) -> {
            int left;
            int top;
            int right;
            int bottom;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(
                        WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout()
                                | WindowInsets.Type.ime());
                left = bars.left;
                top = bars.top;
                right = bars.right;
                bottom = bars.bottom;
            } else {
                left = insets.getSystemWindowInsetLeft();
                top = insets.getSystemWindowInsetTop();
                right = insets.getSystemWindowInsetRight();
                bottom = insets.getSystemWindowInsetBottom();
            }
            view.setPadding(left, top, right, bottom);
            return insets;
        });
        scroll.requestApplyInsets();

        TextView eyebrow = label("EDGE WALKER  /  COMPANION", 11, TEAL, true);
        page.addView(eyebrow);
        TextView title = label("设备状态，随时掌握。", 28, INK, true);
        add(page, title, 8);
        add(page, label("边缘行者 · 手机控制台", 15, MUTED, false), 6);

        LinearLayout notice = new LinearLayout(this);
        notice.setOrientation(LinearLayout.VERTICAL);
        notice.setPadding(dp(15), dp(13), dp(15), dp(13));
        notice.setBackground(shape(Color.rgb(255, 242, 218), 14));
        noticeTitle = label("连接后确认数据来源", 13, ORANGE, true);
        noticeBody = label("可连接本地模拟器或电脑串口网关。\n串口网关仅提供只读状态。", 13,
                Color.rgb(123, 90, 48), false);
        notice.addView(noticeTitle);
        add(notice, noticeBody, 5);
        add(page, notice, 20);

        LinearLayout connection = card(page, "01   连接设备", "连接本地模拟器或只读串口网关");
        connectionTitle = (TextView) connection.getChildAt(0);
        connectionSubtitle = (TextView) connection.getChildAt(1);
        sourceText = label("数据来源：未连接", 13, MUTED, true);
        sourceText.setContentDescription("ew_origin");
        add(connection, sourceText, 13);
        connectionText = label("未连接", 22, INK, true);
        connectionText.setContentDescription("ew_connection");
        add(connection, connectionText, 8);
        connectionDetail = label("尚未连接；收到有效快照后显示设备状态。", 13, MUTED, false);
        add(connection, connectionDetail, 5);
        LinearLayout addressRow = row();
        hostInput = input("主机地址", false);
        hostInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        hostInput.setFilters(new InputFilter[]{new InputFilter.LengthFilter(253)});
        hostInput.setContentDescription("ew_host");
        portInput = input("端口", false);
        portInput.setInputType(InputType.TYPE_CLASS_NUMBER);
        portInput.setFilters(new InputFilter[]{new InputFilter.LengthFilter(5)});
        portInput.setContentDescription("ew_port");
        addressRow.addView(hostInput, new LinearLayout.LayoutParams(0, dp(52), 1f));
        LinearLayout.LayoutParams portParams = new LinearLayout.LayoutParams(dp(92), dp(52));
        portParams.leftMargin = dp(8);
        addressRow.addView(portInput, portParams);
        add(connection, addressRow, 14);
        pairInput = input("连接码（配对网络原型需要，USB或模拟器可留空）", false);
        pairInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        pairInput.setFilters(new InputFilter[]{new InputFilter.LengthFilter(64)});
        pairInput.setContentDescription("ew_pair_code");
        pairInput.setSaveEnabled(false);
        add(connection, pairInput, 8);
        add(connection, label("MuMu：10.0.2.2。实体手机请填写测试时确认的网关或设备地址；加入热点不等于控制服务已开启。", 12, MUTED, false), 8);
        LinearLayout connectRow = row();
        connectButton = button("连接设备", TEAL, true);
        connectButton.setContentDescription("ew_connect");
        disconnectButton = button("断开", INK, false);
        disconnectButton.setContentDescription("ew_disconnect");
        addEqual(connectRow, connectButton, disconnectButton);
        add(connection, connectRow, 12);
        connectButton.setOnClickListener(view -> beginConnect());
        disconnectButton.setOnClickListener(view -> disconnect("已手动断开", false));
        capabilitiesText = label("连接后读取服务端支持的能力。", 12, MUTED, false);
        capabilitiesText.setContentDescription("ew_capabilities");
        add(connection, capabilitiesText, 10);

        LinearLayout state = card(page, "02   设备状态", "连接后显示经过来源核验的状态");
        stateSubtitle = (TextView) state.getChildAt(1);
        LinearLayout metrics = row();
        rangeValue = metric(metrics, "目标距离", "—", "米");
        rangeValue.setContentDescription("ew_range");
        speedValue = metric(metrics, "接近速度", "—", "km/h");
        speedValue.setContentDescription("ew_speed");
        levelValue = metric(metrics, "告警等级", "—", "端侧判决");
        levelValue.setContentDescription("ew_alert_level");
        add(state, metrics, 18);
        radarText = label("雷达链路：尚未收到状态", 13, MUTED, false);
        radarText.setContentDescription("ew_radar");
        add(state, radarText, 16);
        updatedText = label("尚未收到状态", 12, MUTED, false);
        updatedText.setContentDescription("ew_updated");
        add(state, updatedText, 6);
        refreshButton = button("刷新状态", TEAL, false);
        refreshButton.setContentDescription("ew_refresh");
        add(state, refreshButton, 12);
        refreshButton.setOnClickListener(view -> request("get_state", new JSONObject()));

        LinearLayout control = card(page, "03   告警与档位", "测试只作用于模拟器，持续 2 秒");
        controlSubtitle = (TextView) control.getChildAt(1);
        LinearLayout alertRow = row();
        softButton = button("轻度告警 · SOFT", ORANGE, false);
        softButton.setContentDescription("ew_alert_soft");
        strongButton = button("强告警 · STRONG", RED, false);
        strongButton.setContentDescription("ew_alert_strong");
        addEqual(alertRow, softButton, strongButton);
        add(control, alertRow, 15);
        softButton.setOnClickListener(view -> testAlert("soft"));
        strongButton.setOnClickListener(view -> testAlert("strong"));
        profileText = label("当前档位：未知", 13, INK, true);
        profileText.setContentDescription("ew_profile");
        add(control, profileText, 19);
        LinearLayout profileRow = row();
        walkButton = button("步行 · walk", TEAL, false);
        walkButton.setContentDescription("ew_profile_walk");
        cycleButton = button("骑行 · cycle", TEAL, false);
        cycleButton.setContentDescription("ew_profile_cycle");
        addEqual(profileRow, walkButton, cycleButton);
        add(control, profileRow, 8);
        walkButton.setOnClickListener(view -> setProfile("walk"));
        cycleButton.setOnClickListener(view -> setProfile("cycle"));
        actionText = label("尚未发送操作。接收排队与执行完成会分别显示。", 13, MUTED, false);
        actionText.setContentDescription("ew_action");
        actionText.setPadding(dp(12), dp(12), dp(12), dp(12));
        actionText.setBackground(shape(BG, 10));
        add(control, actionText, 16);

        LinearLayout ask = card(page, "04   文字问答", "能力由连接的服务端提供");
        askSubtitle = (TextView) ask.getChildAt(1);
        questionInput = input("例如：告警是怎么工作的？", true);
        questionInput.setFilters(new InputFilter[]{new InputFilter.LengthFilter(500)});
        questionInput.setMinLines(2);
        questionInput.setMaxLines(5);
        questionInput.setGravity(Gravity.TOP | Gravity.START);
        questionInput.setContentDescription("ew_ask_text");
        add(ask, questionInput, 14);
        askButton = button("发送问题", TEAL, true);
        askButton.setContentDescription("ew_ask_send");
        add(ask, askButton, 10);
        replyText = label("连接后可体验模拟问答。", 14, MUTED, false);
        replyText.setContentDescription("ew_reply");
        replyText.setTextIsSelectable(true);
        add(ask, replyText, 15);
        askButton.setOnClickListener(view -> {
            String text = questionInput.getText().toString().trim();
            if (text.isEmpty()) {
                questionInput.setError("请先输入问题");
                return;
            }
            try {
                request("ask", new JSONObject().put("text", text));
                InputMethodManager keyboard = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
                if (keyboard != null) {
                    keyboard.hideSoftInputFromWindow(questionInput.getWindowToken(), 0);
                }
            } catch (JSONException impossible) {
                showAction("问题格式错误", RED);
            }
        });

        LinearLayout events = card(page, "05   最近事件", "保留本次会话最近 36 条记录");
        eventsText = label("", 12, MUTED, false);
        eventsText.setTypeface(Typeface.create("monospace", Typeface.NORMAL));
        eventsText.setTextIsSelectable(true);
        add(events, eventsText, 12);
        add(page, label("首版用于协议与交互验证。真实设备联调仍需独立验收。", 12, MUTED, false), 20);
    }

    private void beginConnect() {
        final String host = hostInput.getText().toString().trim();
        final String portText = portInput.getText().toString().trim();
        int port;
        if (host.isEmpty() || host.contains("://") || host.contains("/") || host.matches(".*\\s.*")) {
            hostInput.setError("请输入主机名或 IP，不含协议、端口和路径");
            return;
        }
        try {
            port = Integer.parseInt(portText);
            if (port < 1 || port > 65535) {
                throw new NumberFormatException();
            }
        } catch (NumberFormatException exception) {
            portInput.setError("端口范围为 1–65535");
            return;
        }
        disconnect(null, false);
        // Event identifiers are scoped to this connection/device, not the app lifetime.
        lastAppliedStateSequence = Long.MIN_VALUE;
        lastEventId = Long.MIN_VALUE;
        lastStateElapsed = 0;
        lastStateOrigin = "";
        lastStateDescription = "尚未收到状态";
        rangeValue.setText("—");
        speedValue.setText("—");
        levelValue.setText("—");
        radarText.setText("雷达链路：尚未收到状态");
        updatedText.setText(lastStateDescription);
        profile = "";
        profileText.setText("当前档位：未知");
        walkButton.setText("步行 · walk");
        cycleButton.setText("骑行 · cycle");
        walkButton.setBackground(shape(BG, 11));
        cycleButton.setBackground(shape(BG, 11));
        resetSourceUi();
        connecting = true;
        connectionText.setText("正在连接…");
        connectionText.setTextColor(ORANGE);
        connectionDetail.setText(host + ":" + port + " · 等待协议握手");
        sourceText.setText("数据来源：等待服务端确认");
        sourceText.setTextColor(MUTED);
        getPreferences(MODE_PRIVATE).edit().putString("host", host).putString("port", portText).apply();
        final int generation = connectionGeneration;
        client = new JsonLineClient(new JsonLineClient.Listener() {
            @Override public void onOpen() {
                main.post(() -> {
                    if (isCurrent(generation)) {
                        appendLog("连接已建立，正在核实数据来源");
                        JSONObject helloArgs = new JSONObject();
                        try {
                            String token = pairInput.getText().toString().trim();
                            if (!token.isEmpty()) helloArgs.put("token", token);
                            request("hello", helloArgs);
                        } catch (JSONException impossible) {
                            disconnect("连接码无效", true);
                        }
                    }
                });
            }
            @Override public void onMessage(JSONObject message) {
                main.post(() -> {
                    if (isCurrent(generation)) {
                        receive(message);
                    }
                });
            }
            @Override public void onFailure(String message) {
                main.post(() -> {
                    if (isCurrent(generation)) {
                        disconnect("连接失败：" + shortText(message, 180), true);
                    }
                });
            }
        });
        appendLog("连接 " + host + ":" + port);
        updateControls();
        client.connect(host, port);
        main.postDelayed(() -> {
            if (isCurrent(generation) && connecting) {
                disconnect("连接或握手超时，请检查服务器", true);
            }
        }, 8000);
    }

    private boolean isCurrent(int generation) {
        return !destroyed && generation == connectionGeneration;
    }

    private void disconnect(String message, boolean error) {
        connectionGeneration++;
        if (client != null) {
            client.close();
            client = null;
        }
        if (!pending.isEmpty()) {
            showAction("连接已结束；未完成请求的执行结果未知。", ORANGE);
        }
        pending.clear();
        connecting = false;
        ready = false;
        subscribed = false;
        capabilities.clear();
        connectionText.setText(error ? "连接异常" : "未连接");
        connectionText.setTextColor(error ? RED : INK);
        connectionDetail.setText(message == null ? "等待连接服务器" : message);
        sourceText.setText(lastStateElapsed == 0 ? "数据来源：未连接"
                : "数据来源：" + originLabel(lastStateOrigin) + " · 历史数据");
        sourceText.setTextColor(MUTED);
        capabilitiesText.setText("尚未连接；操作按钮已停用。");
        rangeValue.setTextColor(MUTED);
        speedValue.setTextColor(MUTED);
        levelValue.setTextColor(MUTED);
        if (lastStateElapsed != 0) {
            updatedText.setText("连接已断开 · 上方为上次" + originLabel(lastStateOrigin) + "数据");
        }
        activeOrigin = "";
        updateControls();
        if (message != null) {
            appendLog(message);
        }
    }

    private void request(String operation, JSONObject args) {
        if (client == null || (!ready && !"hello".equals(operation))) {
            showAction("尚未完成连接，请先连接设备。", ORANGE);
            return;
        }
        if (!"hello".equals(operation) && !allowsOperation(operation)) {
            showAction("当前连接未提供此能力：" + operationLabel(operation), ORANGE);
            return;
        }
        if (pending.size() >= 12 || isPending(operation)) {
            showAction("上一条同类操作尚未完成，请稍候。", ORANGE);
            return;
        }
        String id = sessionId + "-" + (++requestSequence);
        try {
            JSONObject request = new JSONObject().put("v", 1).put("id", id)
                    .put("op", operation).put("args", args);
            pending.put(id, new Pending(operation));
            client.send(request);
            if (!isBackgroundOperation(operation)) {
                showAction(operationLabel(operation) + "：已发送，等待接收", MUTED);
                appendLog("发送 " + operationLabel(operation) + " · " + id);
            }
        } catch (IOException | JSONException exception) {
            pending.remove(id);
            showAction("发送失败：" + shortText(exception.getMessage(), 150), RED);
            appendLog("发送失败 · " + operationLabel(operation));
        }
        updateControls();
    }

    private void receive(JSONObject message) {
        try {
            if (message.getInt("v") != 1) {
                throw new JSONException("不支持的协议版本");
            }
            String type = message.getString("type");
            if ("event".equals(type)) {
                if (ready && "state".equals(message.optString("event"))) {
                    if (!activeOrigin.equals(message.optString("source"))) {
                        throw new JSONException("状态事件来源不匹配");
                    }
                    JSONObject state = message.getJSONObject("data");
                    long expected = nonNegativeInteger(state,
                            hasBoardState() ? "snapshot_seq" : "event_id");
                    if (nonNegativeInteger(message, "event_id") != expected) {
                        throw new JSONException("状态事件序号不匹配");
                    }
                    renderState(state);
                }
                return;
            }
            // Expire before looking up replies, even when the watchdog has not run.
            long receivedAt = SystemClock.elapsedRealtime();
            expirePendingRequests(receivedAt);
            String id = message.getString("id");
            Pending item = pending.get(id);
            if (item == null) {
                appendLog("忽略过期或未知请求的回复 · " + shortText(id, 32));
                return;
            }
            boolean ok = message.getBoolean("ok");
            if ("accepted".equals(type)) {
                if (!ok || !"queued".equals(message.optString("stage"))) {
                    throw new JSONException("接收确认格式错误");
                }
                if (item.waitState.markQueued(receivedAt)) {
                    showAction(operationLabel(item.operation) + "：已接收并排队，尚未执行完成", ORANGE);
                    appendLog("已接收 queued · " + operationLabel(item.operation));
                }
                return;
            }
            if (!"result".equals(type)) {
                throw new JSONException("未知消息类型");
            }
            pending.remove(id);
            if (!ok) {
                JSONObject error = message.optJSONObject("error");
                String code = error == null ? "unknown" : error.optString("code", "unknown");
                String detail = error == null ? "请求失败" : error.optString("message", "请求失败");
                showAction(operationLabel(item.operation) + "：执行失败（" + shortText(code, 48)
                        + "）\n" + shortText(detail, 200), RED);
                appendLog("执行失败 failed · " + operationLabel(item.operation) + " · " + shortText(code, 48));
                if ("hello".equals(item.operation)) {
                    disconnect("握手失败：" + shortText(detail, 150), true);
                }
                updateControls();
                return;
            }
            if (!"applied".equals(message.optString("stage"))) {
                throw new JSONException("最终回复未确认 applied");
            }
            JSONObject data = message.getJSONObject("data");
            applyResult(item.operation, data);
            updateControls();
        } catch (JSONException exception) {
            disconnect("协议错误：" + shortText(exception.getMessage(), 160), true);
        }
    }

    private void applyResult(String operation, JSONObject data) throws JSONException {
        if ("hello".equals(operation)) {
            String origin = data.getString("origin");
            if (!"simulator".equals(origin) && !"pc_gateway".equals(origin) && !"pc_prototype".equals(origin)) {
                throw new JSONException("不支持或未经核验的数据来源");
            }
            if ("pc_prototype".equals(origin) && (!data.getBoolean("prototype")
                    || !("authorized_usb_loopback".equals(data.getString("transport"))
                         || ("paired_lan".equals(data.getString("transport")) && data.getBoolean("paired")
                             && !pairInput.getText().toString().isEmpty()))
                    || !"pc_cloud".equals(data.getString("model_source")))) {
                throw new JSONException("原型服务声明无效");
            }
            JSONArray supported = data.getJSONArray("capabilities");
            if (supported.length() > 32) {
                throw new JSONException("能力列表过长");
            }
            capabilities.clear();
            for (int index = 0; index < supported.length(); index++) {
                String capability = supported.getString(index);
                // A gateway may never advertise its way into write access.
                if ("pc_gateway".equals(origin)) {
                    if (isReadOperation(capability)) {
                        capabilities.add(capability);
                    }
                } else if ("pc_prototype".equals(origin)) {
                    if (isReadOperation(capability) || "get_config".equals(capability)
                            || "set_profile".equals(capability) || "ask".equals(capability)) capabilities.add(capability);
                } else if (isSimulatorOperation(capability)) {
                    capabilities.add(capability);
                }
            }
            if (!capabilities.contains("get_state")) {
                throw new JSONException("服务端未提供状态查询能力");
            }
            int limit = data.getInt("max_message_bytes");
            if (limit < 256) {
                throw new JSONException("消息大小协商失败");
            }
            client.setPeerMaxBytes(limit);
            String deviceId = data.getString("device_id");
            if (deviceId.isEmpty() || deviceId.length() > 128) {
                throw new JSONException("设备标识无效");
            }
            activeOrigin = origin;
            prototypeFixture = isPrototype() && data.getBoolean("fixture_state");
            applySourceUi();
            ready = true;
            connecting = false;
            connectionText.setText("已连接 · " + (isPrototype() ? "电脑转发原型" : isGateway() ? "只读串口网关" : "模拟器"));
            connectionText.setTextColor(TEAL);
            sourceText.setText(isPrototype() ? (prototypeFixture ? "数据来源：协议夹具 · 模拟设备" : "数据来源：真实开发板 / 模型经电脑转发")
                    : isGateway() ? "数据来源：PC 串口网关 · 只读" : "数据来源：本地模拟器");
            sourceText.setTextColor(TEAL);
            connectionDetail.setText("设备 " + shortText(deviceId, 64)
                    + " · " + hostInput.getText() + ":" + portInput.getText());
            capabilitiesText.setText("已协商 " + capabilities.size() + " 项能力；"
                    + (isGateway() ? "当前连接仅可查看状态。" : "未提供的操作保持停用。"));
            appendLog(originLabel(origin) + "握手完成 · 能力 " + capabilities.size() + " 项");
            showAction(isPrototype() ? "原型已连接；敏感度由设备确认，模型请求经电脑转发。" : isGateway() ? "只读连接已建立，可查看和刷新设备状态。"
                    : "已连接模拟器，可体验服务端提供的操作。", TEAL);
            if (capabilities.contains("get_state")) {
                request("get_state", new JSONObject());
            }
            if (capabilities.contains("get_config")) {
                request("get_config", new JSONObject());
            }
            if (capabilities.contains("subscribe_state")) {
                request("subscribe_state", new JSONObject().put("enabled", true));
            }
        } else if ("get_state".equals(operation)) {
            renderState(data);
            appendLog("状态已刷新 applied");
        } else if ("get_config".equals(operation) || "set_profile".equals(operation)) {
            if (isGateway()) {
                throw new JSONException("只读网关不能返回配置操作结果");
            }
            if (isPrototype() && (!activeOrigin.equals(data.getString("origin"))
                    || !data.getBoolean("device_confirmed") || !data.getBoolean("volatile"))) {
                throw new JSONException("缺少设备敏感度确认");
            }
            renderProfile(data.getString("profile"));
            if ("set_profile".equals(operation)) {
                showAction("档位切换：已应用 · " + profileLabel(profile), TEAL);
                appendLog("档位已应用 applied · " + profileLabel(profile));
            }
        } else if ("subscribe_state".equals(operation)) {
            if (!activeOrigin.equals(data.getString("origin"))) {
                throw new JSONException("订阅回复来源不匹配");
            }
            subscribed = data.getBoolean("enabled");
            appendLog(subscribed ? "实时状态订阅已开启 applied" : "实时状态订阅已停止 applied");
        } else if ("test_alert".equals(operation)) {
            if (isGateway()) {
                throw new JSONException("只读网关不能返回告警操作结果");
            }
            JSONObject state = data.optJSONObject("state");
            if (state != null) {
                renderState(state);
            }
            long eventId = data.getLong("event_id");
            showAction("告警测试：已应用 applied · 事件 #" + eventId, TEAL);
            appendLog("告警已应用 applied · 事件 #" + eventId);
        } else if ("ask".equals(operation)) {
            if (!activeOrigin.equals(data.getString("origin"))) {
                throw new JSONException("问答来源不匹配");
            }
            if (isPrototype() && (!"pc_cloud".equals(data.getString("model_source"))
                    || data.getBoolean("model_simulated") != prototypeFixture)) throw new JSONException("模型来源无效");
            replyText.setText((isPrototype() && !prototypeFixture ? "MiMo · 电脑转发\n\n" : "模拟回复 · 非 MiMo\n\n")
                    + shortText(data.getString("reply"), 1600));
            replyText.setTextColor(INK);
            showAction(isPrototype() && !prototypeFixture ? "真实模型回复已返回 applied" : "文字问答：模拟回复已返回 applied", TEAL);
            appendLog(isPrototype() && !prototypeFixture ? "模型回复已返回 · 电脑转发" : "模拟问答已返回 applied");
        }
    }

    private void renderState(JSONObject state) throws JSONException {
        if (activeOrigin.isEmpty() || !activeOrigin.equals(state.getString("origin"))) {
            throw new JSONException("状态来源不匹配");
        }
        long eventId = nonNegativeInteger(state, "event_id");
        long sequence = hasBoardState() ? nonNegativeInteger(state, "snapshot_seq") : eventId;
        // Board event IDs change only on decisions; snapshot_seq orders independent
        // reads. Neither device uptime nor gateway wall-clock time orders snapshots.
        if (sequence < lastAppliedStateSequence) {
            return;
        }
        Double range = measurement(state, "range_m", hasBoardState());
        Double speed = measurement(state, "speed_kmh", hasBoardState());
        boolean connected = state.getBoolean("connected");
        String radar = state.getString("radar_link");
        String radarLabel;
        switch (radar) {
            case "ok": radarLabel = "正常"; break;
            case "waiting": radarLabel = "等待数据"; break;
            case "no_frame": radarLabel = "无有效帧"; break;
            case "stale": radarLabel = "数据已过期"; break;
            case "error": radarLabel = "故障"; break;
            default: throw new JSONException("未知雷达链路状态");
        }
        String level = state.getString("alert_level");
        int color;
        String levelLabel;
        switch (level) {
            case "none":
                levelLabel = hasBoardState() ? "无告警" : "正常";
                color = "ok".equals(radar) ? TEAL : MUTED;
                break;
            case "soft": levelLabel = "轻度"; color = ORANGE; break;
            case "strong": levelLabel = "强告警"; color = RED; break;
            case "emergency": levelLabel = "紧急"; color = RED; break;
            default: throw new JSONException("未知告警等级");
        }
        long updated = nonNegativeInteger(state, "updated_ms");
        String nextProfile;
        long displayTime;
        if (hasBoardState()) {
            if (!"device_monotonic".equals(state.getString("clock"))) {
                throw new JSONException("设备时间基准不匹配");
            }
            displayTime = nonNegativeInteger(state, "received_at_ms");
            if (displayTime == 0 || !state.has("profile") || (isGateway() && !state.isNull("profile"))) {
                throw new JSONException("网关快照元数据无效");
            }
            nextProfile = isPrototype() ? state.getString("profile") : null;
        } else {
            displayTime = updated;
            nextProfile = state.getString("profile");
            if (!"walk".equals(nextProfile) && !"cycle".equals(nextProfile)) {
                throw new JSONException("未知档位");
            }
        }
        // Validate the entire snapshot before changing any displayed fields.
        rangeValue.setText(range == null ? "—" : String.format(Locale.CHINA, "%.1f", range));
        speedValue.setText(speed == null ? "—" : String.format(Locale.CHINA, "%.1f", speed));
        levelValue.setText(levelLabel);
        rangeValue.setTextColor(INK);
        speedValue.setTextColor(INK);
        levelValue.setTextColor(color);
        radarText.setText((hasBoardState() ? "快照链路：" : "模拟设备：") + (connected ? "在线" : "离线")
                + "  ·  雷达：" + radarLabel + (hasBoardState() ? "" : "（模拟）"));
        renderProfile(nextProfile);
        String time = displayTime > 0 ? new SimpleDateFormat("HH:mm:ss", Locale.CHINA)
                .format(new Date(displayTime)) : "未知时间";
        lastStateDescription = "事件 #" + eventId
                + (hasBoardState() ? " · 网关接收 " : " · 更新于 ") + time;
        updatedText.setText(lastStateDescription + (subscribed ? " · 实时订阅" : ""));
        updatedText.setTextColor(MUTED);
        lastStateElapsed = SystemClock.elapsedRealtime();
        lastStateOrigin = activeOrigin;
        lastAppliedStateSequence = sequence;
        if (sequence != lastEventId) {
            appendLog(hasBoardState() ? "网关快照 #" + sequence + " · 告警事件 #" + eventId + " · " + radarLabel
                    : "模拟状态事件 #" + eventId + " · " + levelLabel + " · " + profileLabel(profile));
            lastEventId = sequence;
        }
        updateControls();
    }

    private void renderProfile(String value) throws JSONException {
        if (isPrototype()) {
            if (!"standard".equals(value) && !"early".equals(value)) throw new JSONException("未知敏感度");
            profile = value;
            profileText.setText("设备敏感度：" + profileLabel(value) + "（重启恢复标准）");
            walkButton.setText(("standard".equals(value) ? "✓ " : "") + "标准敏感度");
            cycleButton.setText(("early".equals(value) ? "✓ " : "") + "提前预警 +25%");
            return;
        }
        if (value != null && !"walk".equals(value) && !"cycle".equals(value)) {
            throw new JSONException("未知档位");
        }
        profile = value == null ? "" : value;
        profileText.setText(value == null ? "当前档位：未提供（只读）"
                : "当前档位：" + profileLabel(value) + (isGateway() ? "（只读）" : "（模拟）"));
        walkButton.setText("walk".equals(profile) ? "✓ 步行 · walk" : "步行 · walk");
        cycleButton.setText("cycle".equals(profile) ? "✓ 骑行 · cycle" : "骑行 · cycle");
        walkButton.setBackground(shape("walk".equals(profile) ? PALE : BG, 11));
        cycleButton.setBackground(shape("cycle".equals(profile) ? PALE : BG, 11));
    }

    private void testAlert(String level) {
        try {
            request("test_alert", new JSONObject().put("level", level).put("duration_ms", 2000));
        } catch (JSONException impossible) {
            showAction("告警参数无效", RED);
        }
    }

    private void setProfile(String value) {
        try {
            if (isPrototype()) value = "walk".equals(value) ? "standard" : "early";
            request("set_profile", new JSONObject().put("profile", value));
        } catch (JSONException impossible) {
            showAction("档位参数无效", RED);
        }
    }

    private boolean isGateway() {
        return "pc_gateway".equals(activeOrigin);
    }

    private boolean isPrototype() { return "pc_prototype".equals(activeOrigin); }
    private boolean hasBoardState() { return isGateway() || isPrototype(); }

    private static boolean isReadOperation(String operation) {
        return "get_state".equals(operation) || "subscribe_state".equals(operation);
    }

    private static boolean isSimulatorOperation(String operation) {
        return isReadOperation(operation) || "get_config".equals(operation)
                || "set_profile".equals(operation) || "test_alert".equals(operation)
                || "ask".equals(operation);
    }

    private boolean allowsOperation(String operation) {
        return capabilities.contains(operation)
                && ("simulator".equals(activeOrigin) || (isGateway() && isReadOperation(operation))
                    || (isPrototype() && (isReadOperation(operation) || "get_config".equals(operation)
                       || "set_profile".equals(operation) || "ask".equals(operation))));
    }

    private static long nonNegativeInteger(JSONObject object, String key) throws JSONException {
        Object value = object.get(key);
        if (!(value instanceof Integer) && !(value instanceof Long)) {
            throw new JSONException(key + " 必须为整数");
        }
        long number = ((Number) value).longValue();
        if (number < 0) {
            throw new JSONException(key + " 不得为负数");
        }
        return number;
    }

    private static Double measurement(JSONObject object, String key, boolean nullable) throws JSONException {
        Object value = object.get(key);
        if (value == JSONObject.NULL && nullable) {
            return null;
        }
        if (!(value instanceof Number)) {
            throw new JSONException(key + " 必须为有效数值");
        }
        double number = ((Number) value).doubleValue();
        if (Double.isNaN(number) || Double.isInfinite(number) || number < 0) {
            throw new JSONException(key + " 必须为非负有限数值");
        }
        return number;
    }

    private static String originLabel(String origin) {
        return "pc_prototype".equals(origin) ? "电脑转发原型" : "pc_gateway".equals(origin) ? "PC 串口网关" : "simulator".equals(origin) ? "模拟器" : "未知来源";
    }

    private void resetSourceUi() {
        activeOrigin = "";
        noticeTitle.setText("连接后确认数据来源");
        noticeBody.setText("可连接本地模拟器或电脑串口网关。\n串口网关仅提供只读状态。");
        connectionTitle.setText("01   连接设备");
        connectionSubtitle.setText("连接本地模拟器或只读串口网关");
        connectButton.setText("连接设备");
        stateSubtitle.setText("连接后显示服务端返回的状态");
        controlSubtitle.setText("操作仅在模拟器连接中开放");
        askSubtitle.setText("能力由连接的服务端提供");
        replyText.setText("连接后按服务端能力开放问答。");
        actionText.setText("等待连接；操作按钮已停用。");
    }

    private void applySourceUi() {
        if (isPrototype()) {
            noticeTitle.setText(prototypeFixture ? "协议夹具 · 模拟设备" : "电脑转发原型 · 真实设备");
            noticeBody.setText(prototypeFixture ? "当前数据与操作来自软件夹具，用于协议验证。\n不代表真实开发板或真实MiMo执行。"
                    : "敏感度由开发板修改并读回确认；模型经电脑访问MiMo。\n需要保持电脑和USB连接；尚不是设备独立直连。");
            connectionTitle.setText("01   连接原型网关");
            connectionSubtitle.setText(prototypeFixture ? "软件夹具通道 · 状态、敏感度、模拟问答" : "电脑转发通道 · 状态、敏感度、文字问答");
            connectButton.setText("连接原型");
            stateSubtitle.setText(prototypeFixture ? "模拟设备快照 · 不代表真实雷达测量" : "真实开发板快照 · 缺测保持为空");
            controlSubtitle.setText("标准保持原门限；提前档将距离/TTC门限提高25%，重启恢复标准");
            askSubtitle.setText(prototypeFixture ? "模拟回复 · 非真实 MiMo，不执行设备工具" : "真实MiMo · 电脑转发，不执行设备工具");
            replyText.setText(prototypeFixture ? "发送问题后返回模拟回复。" : "发送问题后等待真实模型回复。");
        } else if (isGateway()) {
            noticeTitle.setText("串口网关 · 只读");
            noticeBody.setText("当前显示网关返回的状态。\n告警、档位与问答在此连接中停用。");
            connectionTitle.setText("01   连接串口网关");
            connectionSubtitle.setText("电脑串口通路 · 仅查询和订阅状态");
            connectButton.setText("连接网关");
            stateSubtitle.setText("来自 PC 串口网关的只读状态");
            controlSubtitle.setText("当前连接仅提供状态，操作按钮已停用");
            askSubtitle.setText("串口网关未提供文字问答");
            replyText.setText("当前只读连接仅提供状态查询和订阅。");
            profileText.setText("当前档位：未提供（只读）");
        } else {
            noticeTitle.setText("模拟体验版");
            noticeBody.setText("当前连接电脑上的设备模拟器。\n告警与问答用于应用功能验证。");
            connectionTitle.setText("01   连接模拟器");
            connectionSubtitle.setText("连接电脑上的模拟设备");
            connectButton.setText("连接模拟器");
            stateSubtitle.setText("仅显示服务端实际返回的模拟数据");
            controlSubtitle.setText("测试只作用于模拟器，持续 2 秒");
            askSubtitle.setText("模拟回复 · 非真实 MiMo");
            replyText.setText("连接后可体验模拟问答。");
        }
        replyText.setTextColor(MUTED);
    }

    private void updateControls() {
        connectButton.setEnabled(!connecting && !ready);
        disconnectButton.setEnabled(connecting || ready);
        hostInput.setEnabled(!connecting && !ready);
        portInput.setEnabled(!connecting && !ready);
        pairInput.setEnabled(!connecting && !ready);
        enable(refreshButton, "get_state");
        enable(softButton, "test_alert");
        enable(strongButton, "test_alert");
        enable(walkButton, "set_profile");
        enable(cycleButton, "set_profile");
        enable(askButton, "ask");
        questionInput.setEnabled(ready && allowsOperation("ask") && !isPending("ask"));
    }

    private void enable(Button button, String operation) {
        boolean enabled = ready && allowsOperation(operation) && !isPending(operation);
        button.setEnabled(enabled);
        button.setAlpha(enabled ? 1f : 0.42f);
    }

    private boolean isPending(String operation) {
        for (Pending item : pending.values()) {
            if (operation.equals(item.operation)) {
                return true;
            }
        }
        return false;
    }

    /** Main-thread only; shared by incoming replies and the periodic watchdog. */
    private void expirePendingRequests(long now) {
        Iterator<Map.Entry<String, Pending>> iterator = pending.entrySet().iterator();
        boolean changed = false;
        boolean helloTimedOut = false;
        while (iterator.hasNext()) {
            Pending item = iterator.next().getValue();
            if (item.waitState.isExpired(now)) {
                iterator.remove();
                changed = true;
                helloTimedOut |= "hello".equals(item.operation);
                showAction(operationLabel(item.operation) + "：等待超时，执行结果未知，请刷新确认", ORANGE);
                appendLog("超时 · " + operationLabel(item.operation)
                        + (item.waitState.isQueued() ? " · 已排队但无最终回复" : " · 无服务端确认"));
            }
        }
        if (helloTimedOut) {
            disconnect("协议握手超时", true);
        } else if (changed) {
            updateControls();
        }
    }

    private final Runnable watchdog = new Runnable() {
        @Override public void run() {
            if (destroyed) {
                return;
            }
            long now = SystemClock.elapsedRealtime();
            expirePendingRequests(now);
            if (ready && lastStateElapsed != 0 && now - lastStateElapsed > 5000) {
                updatedText.setText(lastStateDescription + " · 数据已过期，请刷新");
                updatedText.setTextColor(ORANGE);
            }
            main.postDelayed(this, 1000);
        }
    };

    private static boolean isBackgroundOperation(String operation) {
        return "hello".equals(operation) || "get_state".equals(operation)
                || "get_config".equals(operation) || "subscribe_state".equals(operation);
    }

    private static String operationLabel(String operation) {
        switch (operation) {
            case "hello": return "连接握手";
            case "get_state": return "刷新状态";
            case "get_config": return "读取档位";
            case "subscribe_state": return "订阅状态";
            case "test_alert": return "告警测试";
            case "set_profile": return "档位切换";
            case "ask": return "文字问答";
            default: return operation;
        }
    }

    private static String profileLabel(String value) {
        if ("standard".equals(value)) return "标准敏感度";
        if ("early".equals(value)) return "提前预警 +25%";
        return "walk".equals(value) ? "步行 walk" : "cycle".equals(value) ? "骑行 cycle" : "未提供";
    }

    private void showAction(String message, int color) {
        actionText.setText(message);
        actionText.setTextColor(color);
    }

    private void appendLog(String message) {
        String time = new SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(new Date());
        logLines.add(0, time + "  " + shortText(message, 220));
        while (logLines.size() > MAX_LOG_LINES) {
            logLines.remove(logLines.size() - 1);
        }
        StringBuilder text = new StringBuilder();
        for (String line : logLines) {
            if (text.length() != 0) {
                text.append("\n\n");
            }
            text.append(line);
        }
        eventsText.setText(text.toString());
    }

    private static String shortText(String value, int maxLength) {
        if (value == null) {
            return "未知错误";
        }
        String clean = value.replace('\r', ' ').replace('\u0000', ' ');
        return clean.length() > maxLength ? clean.substring(0, maxLength) + "…" : clean;
    }

    private LinearLayout card(LinearLayout page, String title, String subtitle) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(17), dp(19), dp(17), dp(18));
        card.setBackground(shape(Color.WHITE, 18));
        card.setElevation(dp(1));
        card.addView(label(title, 17, INK, true));
        add(card, label(subtitle, 12, MUTED, false), 5);
        add(page, card, 16);
        return card;
    }

    private TextView metric(LinearLayout row, String title, String value, String unit) {
        LinearLayout group = new LinearLayout(this);
        group.setOrientation(LinearLayout.VERTICAL);
        group.addView(label(title, 11, MUTED, false));
        TextView number = label(value, 24, INK, true);
        add(group, number, 7);
        add(group, label(unit, 11, MUTED, false), 4);
        row.addView(group, new LinearLayout.LayoutParams(0, -2, 1f));
        return number;
    }

    private TextView label(String text, int sizeSp, int color, boolean bold) {
        TextView label = new TextView(this);
        label.setText(text);
        label.setTextSize(sizeSp);
        label.setTextColor(color);
        label.setLineSpacing(dp(3), 1f);
        if (bold) {
            label.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        }
        return label;
    }

    private EditText input(String hint, boolean multiline) {
        EditText edit = new EditText(this);
        edit.setHint(hint);
        edit.setTextSize(14);
        edit.setTextColor(INK);
        edit.setHintTextColor(MUTED);
        edit.setPadding(dp(12), dp(12), dp(12), dp(12));
        edit.setSingleLine(!multiline);
        edit.setInputType(InputType.TYPE_CLASS_TEXT | (multiline
                ? InputType.TYPE_TEXT_FLAG_MULTI_LINE | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES : 0));
        edit.setBackground(shape(BG, 10));
        return edit;
    }

    private Button button(String title, int color, boolean filled) {
        Button button = new Button(this);
        button.setText(title);
        button.setTextSize(12);
        button.setAllCaps(false);
        button.setTextColor(filled ? Color.WHITE : color);
        button.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        button.setMinHeight(dp(48));
        button.setMinimumHeight(dp(48));
        button.setPadding(dp(8), dp(8), dp(8), dp(8));
        button.setBackground(shape(filled ? color : BG, 11));
        button.setStateListAnimator(null);
        return button;
    }

    private LinearLayout row() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        return row;
    }

    private void addEqual(LinearLayout row, View first, View second) {
        row.addView(first, new LinearLayout.LayoutParams(0, -2, 1f));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -2, 1f);
        params.leftMargin = dp(8);
        row.addView(second, params);
    }

    private void add(LinearLayout parent, View child, int marginTopDp) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.topMargin = dp(marginTopDp);
        parent.addView(child, params);
    }

    private GradientDrawable shape(int color, int radiusDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radiusDp));
        return drawable;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onSaveInstanceState(Bundle state) {
        state.putString("question", questionInput.getText().toString());
        super.onSaveInstanceState(state);
    }

    @Override
    protected void onStop() {
        super.onStop();
        if (connecting || ready) {
            disconnect("应用离开前台，连接已关闭；返回后请手动连接。", false);
        }
    }

    @Override
    protected void onDestroy() {
        destroyed = true;
        connectionGeneration++;
        if (client != null) {
            client.close();
            client = null;
        }
        pending.clear();
        main.removeCallbacksAndMessages(null);
        super.onDestroy();
    }
}
