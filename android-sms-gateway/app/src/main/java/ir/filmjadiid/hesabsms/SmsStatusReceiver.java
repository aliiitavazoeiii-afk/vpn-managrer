package ir.filmjadiid.hesabsms;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.telephony.SmsManager;
import android.telephony.SmsMessage;

import org.json.JSONObject;

import java.util.Map;

/**
 * Per-part SMS send/delivery state machine. Serializes Gateway jobs, records
 * independent receipts, never reports delivery merely because send succeeded,
 * and does not automatically retry uncertain sends.
 */
public class SmsStatusReceiver extends BroadcastReceiver {
    public static final String ACTION_SENT = "ir.filmjadiid.hesabsms.SMS_SENT";
    public static final String ACTION_DELIVERED = "ir.filmjadiid.hesabsms.SMS_DELIVERED";
    private static final String STORE = "sms_delivery_state";
    private static final long TIMEOUT_MS = 180_000L;
    private static final long GAP_MS = 8_000L;

    private static String resultName(int code) {
        if (code == Activity.RESULT_OK) return "RESULT_OK";
        if (code == Activity.RESULT_CANCELED) return "RESULT_CANCELED";
        if (code == SmsManager.RESULT_ERROR_LIMIT_EXCEEDED) return "ANDROID_SMS_LIMIT_EXCEEDED";
        if (code == SmsManager.RESULT_RIL_REQUEST_RATE_LIMITED) return "RADIO_REQUEST_RATE_LIMITED";
        if (code == SmsManager.RESULT_ERROR_GENERIC_FAILURE) return "GENERIC_FAILURE";
        if (code == SmsManager.RESULT_ERROR_NO_SERVICE) return "NO_SERVICE";
        if (code == SmsManager.RESULT_ERROR_RADIO_OFF) return "RADIO_OFF";
        return "OTHER_ANDROID_RESULT";
    }

    /**
     * A delivery PendingIntent can have RESULT_OK for a received status report
     * even when that report describes a temporary or permanent failure.
     * Only the SMS-STATUS-REPORT PDU's TP-Status determines delivery.
     *
     * Returns Integer.MIN_VALUE if no authentic, parseable status report exists.
     * Do not log/upload raw PDU: it may include phone number and network data.
     */
    private static int readDeliveryStatus(Intent intent) {
        byte[] pdu = intent.getByteArrayExtra("pdu");
        String format = intent.getStringExtra("format");
        if (pdu == null || pdu.length == 0 ||
                (!SmsMessage.FORMAT_3GPP.equals(format) &&
                 !SmsMessage.FORMAT_3GPP2.equals(format))) {
            return Integer.MIN_VALUE;
        }
        try {
            SmsMessage report = SmsMessage.createFromPdu(pdu, format);
            if (report == null || !report.isStatusReportMessage()) {
                return Integer.MIN_VALUE;
            }
            return report.getStatus();
        } catch (RuntimeException ex) {
            android.util.Log.w("HesabSmsGateway", "Unable to decode SMS delivery report", ex);
            return Integer.MIN_VALUE;
        }
    }

    private static boolean confirmedDelivered(int status, String format) {
        if (SmsMessage.FORMAT_3GPP.equals(format)) {
            // 3GPP TS 23.040 TP-Status 0x00..0x1f: short message received.
            // 0x20..0x3f: pending; 0x40+ is failure.
            return status >= 0 && status < 0x20;
        }
        if (SmsMessage.FORMAT_3GPP2.equals(format)) {
            // Android SmsMessage docs: CDMA receipt success = 2 << 16.
            return status == (2 << 16);
        }
        return false;
    }

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(STORE, Context.MODE_PRIVATE);
    }

    public static synchronized boolean mayClaimNext(Context c) {
        SharedPreferences p = prefs(c);
        if (p.getBoolean("paused", false)) return false;
        long active = p.getLong("active_job", -1L);
        if (active >= 0L) {
            long since = p.getLong("active_since", System.currentTimeMillis());
            if (System.currentTimeMillis() - since > TIMEOUT_MS) {
                p.edit().putBoolean("paused", true)
                        .putString("pause_reason", "No complete SMS sent callback for job " + active)
                        .commit();
            }
            return false;
        }
        long previous = p.getLong("last_dispatch", 0L);
        return System.currentTimeMillis() - previous >= GAP_MS;
    }

    public static synchronized void initJob(Context c, long jobId, int total) {
        SharedPreferences p = prefs(c);
        if (p.getLong("active_job", -1L) >= 0L || p.getBoolean("paused", false))
            throw new IllegalStateException("An SMS job is already in flight/paused");
        p.edit()
                .putLong("active_job", jobId)
                .putLong("active_since", System.currentTimeMillis())
                .putLong("last_dispatch", System.currentTimeMillis())
                .putInt("total_" + jobId, Math.max(1, total))
                .putInt("sent_" + jobId, 0)
                .putInt("delivered_" + jobId, 0)
                .putBoolean("failed_" + jobId, false).commit();
    }

    public static synchronized void stopWithError(Context c, long jobId, String error) {
        SharedPreferences p = prefs(c);
        p.edit().putBoolean("paused", true)
                .putString("pause_reason", error)
                .putLong("active_job", -1L)
                .putBoolean("failed_" + jobId, true).commit();
    }

    /** Only operator-initiated after inspecting the last job; never automatic. */
    public static synchronized void resumeAfterReview(Context c) {
        prefs(c).edit().putBoolean("paused", false)
                .remove("pause_reason")
                .putLong("active_job", -1L)
                .putLong("last_dispatch", System.currentTimeMillis()).commit();
    }

    public static String lastDeliveryDiagnostic(Context c) {
        String report = prefs(c).getString("last_delivery_report", "");
        return report == null || report.isEmpty() ? "" :
                "\n⚠ آخرین گزارش تأییدنشده شبکه:\n" + report;
    }

    public static String queueState(Context c) {
        SharedPreferences p = prefs(c);
        if (p.getBoolean("paused", false))
            return "⛔ صف پیامک متوقف شده: " +
                    p.getString("pause_reason", "خطا؛ نیاز به بررسی دستی");
        long job = p.getLong("active_job", -1L);
        if (job >= 0L) return "⏳ در انتظار نتیجه ارسال پیامک #" + job;
        return "✓ صف آماده است";
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null) return;
        // Persist callback evidence immediately. Network I/O happens later
        // in the foreground GatewayService, never in a short-lived receiver.
        final Context app = context.getApplicationContext();
        final String action = intent.getAction();
        final long jobId = intent.getLongExtra("job_id", -1L);
        final int part = intent.getIntExtra("part", -1);
        final int totalFromIntent = intent.getIntExtra("total", 1);
        final int resultCode = getResultCode();
        final int vendorCode = intent.getIntExtra("errorCode", -1);
        final boolean noDefault = intent.getBooleanExtra("noDefault", false);
        if (jobId < 0L || part < 0 || part > 128) return;
        try {
            if (ACTION_SENT.equals(action)) {
                onSent(app, jobId, part, totalFromIntent, resultCode,
                        vendorCode, noDefault);
            } else if (ACTION_DELIVERED.equals(action)) {
                onDelivered(app, jobId, part, resultCode, intent);
            }
        } catch (Exception ex) {
            android.util.Log.e("HesabSmsGateway", "SMS receipt persistence failed", ex);
        }
    }

    private static void onSent(Context c, long jobId, int part, int requestedTotal,
                               int result, int vendor, boolean noDefault) {
        boolean failed = false;
        boolean completed = false;
        int total;
        synchronized (SmsStatusReceiver.class) {
            SharedPreferences p = prefs(c);
            total = p.getInt("total_" + jobId, 0);
            if (total <= 0 || part >= total || p.getBoolean("failed_" + jobId, false) ||
                    p.getBoolean("sent_seen_" + jobId + "_" + part, false))
                return;
            // Count a specific segment's result ONCE even if Android replays a PendingIntent.
            p.edit().putBoolean("sent_seen_" + jobId + "_" + part, true).commit();
            if (result != Activity.RESULT_OK) {
                failed = true;
                String reason = "SMS_CALLBACK_FAILURE job=" + jobId +
                        " part=" + (part+1) + "/" + total +
                        " requestedTotal=" + requestedTotal +
                        " result=" + result + " (" + resultName(result) + ")" + " errorCode=" + vendor +
                        " noDefault=" + noDefault + " sim=" + Prefs.simId(c);
                stopWithError(c, jobId, reason);
            } else if (!p.getBoolean("failed_" + jobId, false)) {
                int done = p.getInt("sent_" + jobId, 0) + 1;
                p.edit().putInt("sent_" + jobId, done).commit();
                if (done == total) {
                    completed = true;
                    if (p.getLong("active_job", -1L) == jobId)
                        p.edit().putLong("active_job", -1L).commit();
                }
            }
        }
        if (failed) {
            String details = "SMS part " + (part+1) + "/" + total + ": result=" +
                    result + " (" + resultName(result) + ")" + "; vendor=" + vendor + "; noDefault=" + noDefault +
                    "; SIM=" + Prefs.simId(c);
            enqueueStatus(c, jobId, "failed", details);
        } else if (completed) {
            enqueueStatus(c, jobId, "sent", "");
        }
    }

    private static void onDelivered(Context c, long jobId, int part,
                                    int callbackResult, Intent intent) {
        // RESULT_OK merely reports callback completion. Verify the network
        // status report; otherwise the dashboard can show false "delivered".
        int status = readDeliveryStatus(intent);
        String format = intent.getStringExtra("format");
        if (callbackResult != Activity.RESULT_OK ||
                !confirmedDelivered(status, format)) {
            String problem = "SMS delivery NOT confirmed: job=" + jobId
                    + " part=" + (part + 1)
                    + " callback=" + callbackResult
                    + " TP-Status=" + (status == Integer.MIN_VALUE ? "missing/invalid" : status)
                    + " format=" + (format == null ? "unknown" : format);
            // A negative receipt does not mean the SMS failed to leave the
            // phone. Never report "failed" or auto-retry a sent SMS here.
            prefs(c).edit().putString("last_delivery_report", problem).commit();
            android.util.Log.w("HesabSmsGateway", problem);

            // 3GPP terminal failure report means we should review before
            // submitting additional customer reminders.
            if (SmsMessage.FORMAT_3GPP.equals(format)
                    && status >= 0x40 && status <= 0x7f) {
                synchronized (SmsStatusReceiver.class) {
                    prefs(c).edit().putBoolean("paused", true)
                            .putString("pause_reason", "Carrier delivery failure: job="
                                    + jobId + " part=" + (part + 1)
                                    + " TP-Status=" + status).commit();
                }
            }
            return;
        }
        boolean completed = false;
        synchronized (SmsStatusReceiver.class) {
            SharedPreferences p = prefs(c);
            int total = p.getInt("total_" + jobId, 0);
            if (total <= 0 || part >= total ||
                    p.getBoolean("delivered_seen_" + jobId + "_" + part, false) ||
                    p.getBoolean("failed_" + jobId, false)) return;
            int delivered = p.getInt("delivered_" + jobId, 0) + 1;
            p.edit().putBoolean("delivered_seen_" + jobId + "_" + part, true)
                    .putInt("delivered_" + jobId, delivered).commit();
            completed = delivered == total;
        }
        if (completed) {
            enqueueStatus(c, jobId, "delivered", "");
        }
    }

    private static synchronized void clearJob(Context c, long jobId) {
        SharedPreferences p = prefs(c);
        SharedPreferences.Editor edit = p.edit();
        for (int i = 0; i < p.getInt("total_" + jobId, 0); i++) {
            edit.remove("sent_seen_" + jobId + "_" + i);
            edit.remove("delivered_seen_" + jobId + "_" + i);
        }
        edit.remove("total_" + jobId).remove("sent_" + jobId)
                .remove("delivered_" + jobId).remove("failed_" + jobId)
                .remove("pending_" + jobId + "_sent")
                .remove("pending_" + jobId + "_delivered")
                .remove("pending_" + jobId + "_failed").commit();
    }

    private static void enqueueStatus(Context c, long jobId, String status, String error) {
        // Durable outbox; the foreground service flushes it over HTTPS.
        // This avoids the Android BroadcastReceiver lifetime/network timeout.
        try {
            JSONObject obj = new JSONObject();
            obj.put("job_id", jobId);
            obj.put("status", status);
            obj.put("error", error == null ? "" : error);
            obj.put("sim_id", Prefs.simId(c));
            prefs(c).edit().putString(
                    "pending_" + jobId + "_" + status, obj.toString()).commit();
        } catch (Exception ex) {
            android.util.Log.e("HesabSmsGateway", "Failed to persist SMS status", ex);
        }
    }

    public static void flushPending(Context c) {
        SharedPreferences p = prefs(c);
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
                    p.edit().remove(entry.getKey()).commit();
                    if ("delivered".equals(status)) clearJob(c, jobId);
                }
            } catch (Exception ignored) {}
        }
    }
}
