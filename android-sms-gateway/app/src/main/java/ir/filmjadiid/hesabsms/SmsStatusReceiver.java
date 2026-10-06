package ir.filmjadiid.hesabsms;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

import org.json.JSONObject;

import java.util.Map;

public class SmsStatusReceiver extends BroadcastReceiver {
    public static final String ACTION_SENT = "ir.filmjadiid.hesabsms.SMS_SENT";
    public static final String ACTION_DELIVERED = "ir.filmjadiid.hesabsms.SMS_DELIVERED";
    private static final String STORE = "sms_delivery_state";

    public static void initJob(Context c, long jobId, int total) {
        SharedPreferences.Editor e = c.getSharedPreferences(STORE, Context.MODE_PRIVATE).edit();
        e.putInt("total_" + jobId, Math.max(1, total));
        e.putInt("sent_" + jobId, 0);
        e.putInt("delivered_" + jobId, 0);
        e.putBoolean("failed_" + jobId, false);
        e.apply();
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        final PendingResult pending = goAsync();
        final Context app = context.getApplicationContext();
        final String action = intent.getAction();
        final long jobId = intent.getLongExtra("job_id", -1L);
        final int result = getResultCode();

        new Thread(() -> {
            try {
                if (jobId < 0) return;
                SharedPreferences p = app.getSharedPreferences(STORE, Context.MODE_PRIVATE);
                if (p.getBoolean("failed_" + jobId, false)) return;

                if (ACTION_SENT.equals(action)) {
                    if (result != Activity.RESULT_OK) {
                        p.edit().putBoolean("failed_" + jobId, true).apply();
                        reportOrQueue(app, jobId, "failed", "Android SMS send result=" + result);
                        return;
                    }
                    int n;
                    int total;
                    synchronized (SmsStatusReceiver.class) {
                        n = p.getInt("sent_" + jobId, 0) + 1;
                        total = p.getInt("total_" + jobId, 1);
                        p.edit().putInt("sent_" + jobId, n).apply();
                    }
                    if (n >= total) {
                        reportOrQueue(app, jobId, "sent", "");
                    }
                } else if (ACTION_DELIVERED.equals(action)) {
                    if (result != Activity.RESULT_OK) return;
                    int n;
                    int total;
                    synchronized (SmsStatusReceiver.class) {
                        n = p.getInt("delivered_" + jobId, 0) + 1;
                        total = p.getInt("total_" + jobId, 1);
                        p.edit().putInt("delivered_" + jobId, n).apply();
                    }
                    if (n >= total) {
                        if (reportOrQueue(app, jobId, "delivered", "")) {
                            clearJob(app, jobId);
                        }
                    }
                }
            } finally {
                pending.finish();
            }
        }, "sms-status-" + jobId).start();
    }

    private static void clearJob(Context c, long jobId) {
        c.getSharedPreferences(STORE, Context.MODE_PRIVATE).edit()
                .remove("total_" + jobId)
                .remove("sent_" + jobId)
                .remove("delivered_" + jobId)
                .remove("failed_" + jobId)
                .remove("pending_" + jobId + "_sent")
                .remove("pending_" + jobId + "_delivered")
                .remove("pending_" + jobId + "_failed")
                .apply();
    }

    private static boolean reportOrQueue(Context c, long jobId, String status, String error) {
        int simId = Prefs.simId(c);
        boolean ok = false;
        for (int i = 0; i < 3 && !ok; i++) {
            ok = ApiClient.reportStatus(c, jobId, status, error, simId);
            if (!ok) {
                try { Thread.sleep(1200L * (i + 1)); } catch (InterruptedException ignored) {}
            }
        }
        if (!ok) {
            try {
                JSONObject j = new JSONObject();
                j.put("job_id", jobId);
                j.put("status", status);
                j.put("error", error == null ? "" : error);
                j.put("sim_id", simId);
                c.getSharedPreferences(STORE, Context.MODE_PRIVATE)
                        .edit()
                        .putString("pending_" + jobId + "_" + status, j.toString())
                        .apply();
            } catch (Exception ignored) {}
        }
        return ok;
    }

    public static void flushPending(Context c) {
        SharedPreferences p = c.getSharedPreferences(STORE, Context.MODE_PRIVATE);
        Map<String, ?> all = p.getAll();
        for (Map.Entry<String, ?> entry : all.entrySet()) {
            if (!entry.getKey().startsWith("pending_")) continue;
            if (!(entry.getValue() instanceof String)) continue;
            try {
                JSONObject j = new JSONObject((String) entry.getValue());
                long jobId = j.getLong("job_id");
                String status = j.getString("status");
                String error = j.optString("error", "");
                int simId = j.optInt("sim_id", -1);
                if (ApiClient.reportStatus(c, jobId, status, error, simId)) {
                    p.edit().remove(entry.getKey()).apply();
                    if ("delivered".equals(status)) clearJob(c, jobId);
                }
            } catch (Exception ignored) {}
        }
    }
}
