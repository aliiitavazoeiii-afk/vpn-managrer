package ir.filmjadiid.hesabsms;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.provider.Telephony;

/**
 * Phone-local callbacks. No personal phone number/message is ever sent to
 * Hesab cloud; delivery status stays in Android's own SMS database.
 */
public class ManualSmsStatusReceiver extends BroadcastReceiver {
    public static final String SENT = "ir.filmjadiid.hesabsms.LOCAL_SENT";
    public static final String DELIVERED = "ir.filmjadiid.hesabsms.LOCAL_DELIVERED";
    private static final String PREF = "hesab_personal_receipts";

    public static synchronized void init(Context c, long id, int parts) {
        c.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
                .putInt("total." + id, parts)
                .putInt("sent." + id, 0)
                .putInt("delivered." + id, 0)
                .putBoolean("failure." + id, false).commit();
    }

    private static void update(Context c, long id, int type, int status) {
        ContentValues values = new ContentValues();
        values.put(Telephony.Sms.TYPE, type);
        values.put(Telephony.Sms.STATUS, status);
        c.getContentResolver().update(
                Uri.withAppendedPath(Telephony.Sms.CONTENT_URI, String.valueOf(id)),
                values, null, null);
    }

    public static synchronized void markImmediateFailure(Context c, long id) {
        c.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit()
                .putBoolean("failure." + id, true).commit();
        update(c, id, Telephony.Sms.MESSAGE_TYPE_FAILED, Telephony.Sms.STATUS_FAILED);
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null) return;
        long id = intent.getLongExtra("id", -1);
        int part = intent.getIntExtra("part", -1);
        if (id < 0 || part < 0 || part > 128) return;
        final Context app = context.getApplicationContext();
        boolean ok = getResultCode() == Activity.RESULT_OK;
        String key = (DELIVERED.equals(intent.getAction()) ? "delivered." : "sent.") + id;
        String seen = "part." + key + "." + part;
        synchronized (ManualSmsStatusReceiver.class) {
            SharedPreferences p = app.getSharedPreferences(PREF, Context.MODE_PRIVATE);
            int total = p.getInt("total." + id, 0);
            if (total <= 0 || part >= total || p.getBoolean(seen, false)) return;
            if (!ok) {
                if (SENT.equals(intent.getAction())) markImmediateFailure(app, id);
                return;
            }
            if (p.getBoolean("failure." + id, false)) return;
            int received = p.getInt(key, 0) + 1;
            p.edit().putBoolean(seen, true).putInt(key, received).commit();
            if (received >= total) {
                if (DELIVERED.equals(intent.getAction())) {
                    update(app, id, Telephony.Sms.MESSAGE_TYPE_SENT,
                            Telephony.Sms.STATUS_COMPLETE);
                } else if (SENT.equals(intent.getAction()) &&
                        p.getInt("delivered." + id, 0) < total) {
                    update(app, id, Telephony.Sms.MESSAGE_TYPE_SENT,
                            Telephony.Sms.STATUS_PENDING);
                }
            }
        }
    }
}
