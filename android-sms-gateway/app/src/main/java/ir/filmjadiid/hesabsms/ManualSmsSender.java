package ir.filmjadiid.hesabsms;

import android.Manifest;
import android.app.PendingIntent;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.provider.Telephony;
import android.telephony.SmsManager;

import java.util.ArrayList;

/** Manual personal messages are phone-local and NEVER enter the dashboard queue. */
public final class ManualSmsSender {
    private ManualSmsSender() {}

    private static String number(String raw) {
        String s = raw == null ? "" : raw.replace(" ", "").replace("-", "");
        final String latin = "0123456789", fa = "۰۱۲۳۴۵۶۷۸۹", ar = "٠١٢٣٤٥٦٧٨٩";
        StringBuilder out = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            int k = fa.indexOf(ch);
            if (k < 0) k = ar.indexOf(ch);
            if (k >= 0) ch = latin.charAt(k);
            out.append(ch);
        }
        s = out.toString();
        if (!s.matches("\\+?[0-9]{8,16}"))
            throw new IllegalArgumentException("Invalid SMS recipient");
        return s;
    }

    @SuppressWarnings("deprecation")
    public static void send(Context context, String recipient, String body) {
        Context app = context.getApplicationContext();
        String phone = number(recipient);
        if (body == null || body.trim().isEmpty() || body.length() > 1400)
            throw new IllegalArgumentException("Invalid SMS text");
        if (!app.getPackageName().equals(Telephony.Sms.getDefaultSmsPackage(app)))
            throw new IllegalStateException("Make Hesab the default SMS app before sending");
        if (app.checkSelfPermission(Manifest.permission.SEND_SMS)
                != PackageManager.PERMISSION_GRANTED)
            throw new SecurityException("SMS permission missing");
        ContentValues values = new ContentValues();
        values.put(Telephony.Sms.ADDRESS, phone);
        values.put(Telephony.Sms.BODY, body);
        values.put(Telephony.Sms.DATE, System.currentTimeMillis());
        values.put(Telephony.Sms.READ, 1);
        values.put(Telephony.Sms.SEEN, 1);
        values.put(Telephony.Sms.TYPE, Telephony.Sms.MESSAGE_TYPE_OUTBOX);
        Uri uri = app.getContentResolver().insert(Telephony.Sms.Outbox.CONTENT_URI, values);
        if (uri == null) throw new IllegalStateException("Cannot save local SMS outbox row");
        long messageId;
        try {
            messageId = Long.parseLong(uri.getLastPathSegment());
        } catch (Exception ex) {
            throw new IllegalStateException("Bad local SMS provider row", ex);
        }
        int subscriptionId = Prefs.simId(app);
        SmsManager manager = subscriptionId >= 0 ?
                SmsManager.getSmsManagerForSubscriptionId(subscriptionId) : SmsManager.getDefault();
        ArrayList<String> parts = manager.divideMessage(body);
        if (parts == null || parts.size() == 0)
            throw new IllegalArgumentException("SMS encoding failed");
        ManualSmsStatusReceiver.init(app, messageId, parts.size());
        try {
            if (parts.size() == 1) {
                manager.sendTextMessage(phone, null, parts.get(0),
                        callback(app, messageId, 0, false),
                        callback(app, messageId, 0, true));
                return;
            }
            ArrayList<PendingIntent> sent = new ArrayList<>();
            ArrayList<PendingIntent> delivered = new ArrayList<>();
            for (int part = 0; part < parts.size(); part++) {
                sent.add(callback(app, messageId, part, false));
                delivered.add(callback(app, messageId, part, true));
            }
            manager.sendMultipartTextMessage(phone, null, parts, sent, delivered);
        } catch (Exception ex) {
            ManualSmsStatusReceiver.markImmediateFailure(app, messageId);
            throw ex;
        }
    }

    private static PendingIntent callback(Context c, long id, int part, boolean delivery) {
        Intent intent = new Intent(c, ManualSmsStatusReceiver.class);
        intent.setAction(delivery ? ManualSmsStatusReceiver.DELIVERED : ManualSmsStatusReceiver.SENT);
        intent.setData(Uri.parse("hesab-message://receipt/" + id + "/" + part +
                (delivery ? "/delivered" : "/sent")));
        intent.putExtra("id", id);
        intent.putExtra("part", part);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        flags |= Build.VERSION.SDK_INT >= 31 ?
                PendingIntent.FLAG_MUTABLE : PendingIntent.FLAG_IMMUTABLE;
        return PendingIntent.getBroadcast(c, 0, intent, flags);
    }
}
