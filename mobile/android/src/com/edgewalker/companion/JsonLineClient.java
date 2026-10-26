/* SPDX-License-Identifier: Apache-2.0 */
package com.edgewalker.companion;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/** Bounded UTF-8 JSONL transport. All listener calls originate on worker threads. */
final class JsonLineClient {
    static final int MAX_MESSAGE_BYTES = 8192;
    private static final int CONNECT_TIMEOUT_MS = 5000;
    private static final int PARTIAL_LINE_TIMEOUT_MS = 5000;

    interface Listener {
        void onOpen();
        void onMessage(JSONObject message);
        void onFailure(String message);
    }

    private final Listener listener;
    private final AtomicBoolean closed = new AtomicBoolean(false);
    private final ThreadPoolExecutor writer = new ThreadPoolExecutor(
            1, 1, 0L, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<Runnable>(16),
            task -> {
                Thread thread = new Thread(task, "ew-jsonl-writer");
                thread.setDaemon(true);
                return thread;
            });
    private volatile Socket socket;
    private volatile int peerMaxBytes = MAX_MESSAGE_BYTES;

    JsonLineClient(Listener listener) {
        this.listener = listener;
    }

    void connect(final String host, final int port) {
        Thread reader = new Thread(() -> {
            Socket connection = new Socket();
            socket = connection;
            try {
                if (closed.get()) {
                    connection.close();
                    return;
                }
                connection.connect(new InetSocketAddress(host, port), CONNECT_TIMEOUT_MS);
                connection.setSoTimeout(1000);
                connection.setTcpNoDelay(true);
                if (closed.get()) {
                    return;
                }
                listener.onOpen();
                BufferedInputStream input = new BufferedInputStream(connection.getInputStream());
                while (!closed.get()) {
                    String line = readBoundedLine(input);
                    if (line == null) {
                        throw new IOException("服务器已关闭连接");
                    }
                    if (line.isEmpty()) {
                        throw new IOException("收到空消息");
                    }
                    try {
                        listener.onMessage(new JSONObject(line));
                    } catch (JSONException exception) {
                        throw new IOException("服务器返回无效 JSON");
                    }
                }
            } catch (IOException | RuntimeException exception) {
                fail(describe(exception));
            } finally {
                closeSocket(connection);
            }
        }, "ew-jsonl-reader");
        reader.setDaemon(true);
        reader.start();
    }

    void setPeerMaxBytes(int bytes) {
        peerMaxBytes = Math.min(MAX_MESSAGE_BYTES, Math.max(256, bytes));
    }

    void send(JSONObject message) throws IOException {
        final byte[] bytes = (message.toString() + "\n").getBytes(StandardCharsets.UTF_8);
        if (bytes.length - 1 > peerMaxBytes) {
            throw new IOException("请求超过消息大小限制");
        }
        if (closed.get()) {
            throw new IOException("连接已关闭");
        }
        try {
            writer.execute(() -> {
                try {
                    Socket connection = socket;
                    if (closed.get() || connection == null || !connection.isConnected()) {
                        throw new IOException("连接未就绪");
                    }
                    OutputStream output = connection.getOutputStream();
                    output.write(bytes);
                    output.flush();
                } catch (IOException | RuntimeException exception) {
                    fail(describe(exception));
                }
            });
        } catch (RejectedExecutionException exception) {
            throw new IOException("发送队列已满，请稍后重试");
        }
    }

    private String readBoundedLine(BufferedInputStream input) throws IOException {
        ByteArrayOutputStream line = new ByteArrayOutputStream(256);
        long startedNs = 0;
        while (!closed.get()) {
            if (startedNs != 0 && TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedNs) > PARTIAL_LINE_TIMEOUT_MS) {
                throw new IOException("服务器消息接收超时");
            }
            int value;
            try {
                value = input.read();
            } catch (SocketTimeoutException timeout) {
                continue;
            }
            if (value == -1) {
                if (line.size() != 0) {
                    throw new IOException("连接中断，消息不完整");
                }
                return null;
            }
            if (value == '\n') {
                byte[] bytes = line.toByteArray();
                int length = bytes.length;
                if (length > 0 && bytes[length - 1] == '\r') {
                    length--;
                }
                try {
                    return StandardCharsets.UTF_8.newDecoder()
                            .onMalformedInput(CodingErrorAction.REPORT)
                            .onUnmappableCharacter(CodingErrorAction.REPORT)
                            .decode(ByteBuffer.wrap(bytes, 0, length)).toString();
                } catch (CharacterCodingException exception) {
                    throw new IOException("服务器消息不是有效 UTF-8");
                }
            }
            if (line.size() >= MAX_MESSAGE_BYTES) {
                throw new IOException("服务器消息超过 8192 字节，已断开");
            }
            if (startedNs == 0) {
                startedNs = System.nanoTime();
            }
            line.write(value);
        }
        return null;
    }

    private void fail(String reason) {
        if (closed.compareAndSet(false, true)) {
            closeSocket(socket);
            writer.shutdownNow();
            listener.onFailure(reason);
        }
    }

    void close() {
        closed.set(true);
        closeSocket(socket);
        writer.shutdownNow();
    }

    private static void closeSocket(Socket connection) {
        if (connection != null) {
            try {
                connection.close();
            } catch (IOException ignored) {
                // Cancellation must not resurrect a closed Activity.
            }
        }
    }

    private static String describe(Exception exception) {
        if (exception instanceof SocketTimeoutException) {
            return "连接超时，请确认地址、端口与服务器";
        }
        String message = exception.getMessage();
        return message == null ? exception.getClass().getSimpleName() : message;
    }
}
