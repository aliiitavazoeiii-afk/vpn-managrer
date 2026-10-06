package ir.filmjadiid.hesabsms;

import android.content.Context;
import android.os.Build;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URLEncoder;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public final class ApiClient {
    private ApiClient() {}

    public static final class SmsJob {
        public final long id;
        public final String phone;
        public final String message;

        SmsJob(long id, String phone, String message) {
            this.id = id;
            this.phone = phone;
            this.message = message;
        }
    }

    private static final class Resp {
        final int code;
        final String body;
        Resp(int code, String body) {
            this.code = code;
            this.body = body;
        }
    }

    private static Resp request(Context c, String method, String path, JSONObject body, boolean auth) throws Exception {
        URL url = new URL(Prefs.baseUrl(c) + path);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setConnectTimeout(10000);
        conn.setReadTimeout(15000);
        conn.setRequestMethod(method);
        conn.setRequestProperty("Accept", "application/json");
        if (auth) conn.setRequestProperty("X-SMS-Gateway-Token", Prefs.token(c));

        if (body != null) {
            byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            conn.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream out = conn.getOutputStream()) {
                out.write(bytes);
            }
        }

        int code = conn.getResponseCode();
        if (code == 204) {
            conn.disconnect();
            return new Resp(code, "");
        }

        InputStream in = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
        String text = "";
        if (in != null) {
            try (InputStream stream = in; ByteArrayOutputStream buf = new ByteArrayOutputStream()) {
                byte[] tmp = new byte[4096];
                int n;
                while ((n = stream.read(tmp)) != -1) buf.write(tmp, 0, n);
                text = buf.toString(StandardCharsets.UTF_8.name());
            }
        }
        conn.disconnect();
        return new Resp(code, text);
    }

    public static boolean ping(Context c) {
        try {
            Resp r = request(c, "GET", "/sms-gateway/health", null, false);
            return r.code == 200;
        } catch (Exception e) {
            return false;
        }
    }

    public static boolean heartbeat(Context c) {
        try {
            JSONObject j = new JSONObject();
            j.put("device_id", Prefs.deviceId(c));
            j.put("device_name", Prefs.deviceName(c));
            j.put("app_version", BuildConfig.VERSION_NAME);
            j.put("android_version", Build.VERSION.RELEASE == null ? "" : Build.VERSION.RELEASE);
            int simId = Prefs.simId(c);
            if (simId >= 0) j.put("sim_subscription_id", simId);
            else j.put("sim_subscription_id", JSONObject.NULL);

            Resp r = request(c, "POST", "/sms-gateway/v1/heartbeat", j, true);
            return r.code >= 200 && r.code < 300;
        } catch (Exception e) {
            return false;
        }
    }

    public static SmsJob poll(Context c) throws Exception {
        String device = URLEncoder.encode(Prefs.deviceId(c), StandardCharsets.UTF_8.name());
        Resp r = request(c, "GET", "/sms-gateway/v1/jobs/next?device_id=" + device, null, true);
        if (r.code == 204) return null;
        if (r.code != 200) throw new IllegalStateException("poll HTTP " + r.code + " " + r.body);

        JSONObject j = new JSONObject(r.body);
        return new SmsJob(j.getLong("id"), j.getString("phone"), j.getString("message"));
    }

    public static boolean reportStatus(Context c, long jobId, String status, String error, int simId) {
        try {
            JSONObject j = new JSONObject();
            j.put("device_id", Prefs.deviceId(c));
            j.put("status", status);
            j.put("error", error == null ? "" : error);
            if (simId >= 0) j.put("sim_subscription_id", simId);
            else j.put("sim_subscription_id", JSONObject.NULL);

            Resp r = request(c, "POST", "/sms-gateway/v1/jobs/" + jobId + "/status", j, true);
            return r.code >= 200 && r.code < 300;
        } catch (Exception e) {
            return false;
        }
    }
}
