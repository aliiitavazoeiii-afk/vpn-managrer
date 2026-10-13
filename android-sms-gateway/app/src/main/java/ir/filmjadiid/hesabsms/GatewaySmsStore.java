package ir.filmjadiid.hesabsms;

import android.content.ContentValues;
import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import android.provider.Telephony;

/**
 * Keeps work SMS in the *phone's* conversation database only when Hesab is
 * the default SMS app. Phone numbers and SMS bodies are NOT synced to server
 * by this component. Backend already owns the original work-SMS job.
 */
public final class GatewaySmsStore {
    private static final String NAME = "hesab_work_sms_provider_rows";
    private GatewaySmsStore() {}

    private static SharedPreferences p(Context c) {
        return c.getSharedPreferences(NAME, Context.MODE_PRIVATE);
    }

    public static synchronized void queue(Context c, long jobId, String phone, String message) {
        if (!c.getPackageName().equals(Telephony.Sms.getDefaultSmsPackage(c))) return;
        if (p(c).contains("uri." + jobId)) return;
        ContentValues values = new ContentValues();
        values.put(Telephony.Sms.ADDRESS, phone);
        values.put(Telephony.Sms.BODY, message);
        values.put(Telephony.Sms.DATE, System.currentTimeMillis());
        values.put(Telephony.Sms.READ, 1);
        values.put(Telephony.Sms.SEEN, 1);
        values.put(Telephony.Sms.TYPE, Telephony.Sms.MESSAGE_TYPE_OUTBOX);
        Uri stored = c.getContentResolver().insert(Telephony.Sms.Outbox.CONTENT_URI, values);
        if (stored == null) throw new IllegalStateException("Cannot save work SMS in phone");
        p(c).edit().putString("uri." + jobId, stored.toString()).commit();
    }

    public static synchronized void failed(Context c, long jobId) {
        change(c, jobId, Telephony.Sms.MESSAGE_TYPE_FAILED,
                Telephony.Sms.STATUS_FAILED, false);
    }

    public static synchronized void sent(Context c, long jobId) {
        if (p(c).getBoolean("delivered." + jobId, false)) return;
        change(c, jobId, Telephony.Sms.MESSAGE_TYPE_SENT,
                Telephony.Sms.STATUS_PENDING, false);
    }

    public static synchronized void delivered(Context c, long jobId) {
        change(c, jobId, Telephony.Sms.MESSAGE_TYPE_SENT,
                Telephony.Sms.STATUS_COMPLETE, true);
    }

    private static void change(Context c, long jobId, int type, int status, boolean delivered) {
        String stored = p(c).getString("uri." + jobId, "");
        if (stored.isEmpty()) return;
        ContentValues values = new ContentValues();
        values.put(Telephony.Sms.TYPE, type);
        values.put(Telephony.Sms.STATUS, status);
        try {
            c.getContentResolver().update(Uri.parse(stored), values, null, null);
            if (delivered) p(c).edit().putBoolean("delivered." + jobId, true).commit();
        } catch (Exception e) {
            android.util.Log.e("HesabSMS", "Local work-SMS status update failed", e);
        }
    }
}
