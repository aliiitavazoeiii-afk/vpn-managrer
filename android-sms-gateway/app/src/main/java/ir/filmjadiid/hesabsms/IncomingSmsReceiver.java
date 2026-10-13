package ir.filmjadiid.hesabsms;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.provider.Telephony;
import android.telephony.SmsMessage;

/**
 * Receives SMS_DELIVER exclusively as the user-selected default SMS app.
 * Stores messages in Android's SMS provider, NEVER on the Hesab server.
 */
public class IncomingSmsReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null ||
                !Telephony.Sms.Intents.SMS_DELIVER_ACTION.equals(intent.getAction())) return;
        SmsMessage[] pieces = Telephony.Sms.Intents.getMessagesFromIntent(intent);
        if (pieces == null || pieces.length == 0) return;
        String sender = pieces[0].getDisplayOriginatingAddress();
        if (sender == null || sender.isEmpty()) return;
        StringBuilder message = new StringBuilder();
        for (SmsMessage part : pieces) {
            if (part != null) message.append(part.getDisplayMessageBody());
        }
        ContentValues values = new ContentValues();
        values.put(Telephony.Sms.ADDRESS, sender);
        values.put(Telephony.Sms.BODY, message.toString());
        values.put(Telephony.Sms.DATE, System.currentTimeMillis());
        values.put(Telephony.Sms.READ, 0);
        values.put(Telephony.Sms.SEEN, 0);
        values.put(Telephony.Sms.TYPE, Telephony.Sms.MESSAGE_TYPE_INBOX);
        try {
            if (context.getContentResolver().insert(Telephony.Sms.Inbox.CONTENT_URI, values) == null)
                return;
            NotificationManager nm =
                    (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm == null) return;
            final String channel = "hesab_personal_sms";
            if (Build.VERSION.SDK_INT >= 26) {
                NotificationChannel ch = new NotificationChannel(channel,
                        "پیامک‌های دریافتی", NotificationManager.IMPORTANCE_DEFAULT);
                nm.createNotificationChannel(ch);
            }
            Intent open = new Intent(context, MessagesActivity.class);
            open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            PendingIntent pi = PendingIntent.getActivity(context, 0, open,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            Notification n = new Notification.Builder(context, channel)
                    .setSmallIcon(android.R.drawable.stat_notify_chat)
                    .setContentTitle("پیام جدید از " + sender)
                    .setContentText("برای مشاهده پیام وارد Hesab Messages شوید.")
                    .setContentIntent(pi).setAutoCancel(true).build();
            nm.notify((int)(System.currentTimeMillis() % Integer.MAX_VALUE), n);
        } catch (SecurityException ex) {
            // This should only occur before SMS role/permissions are granted.
            android.util.Log.e("HesabSMS", "Inbox permission not available", ex);
        }
    }
}
