package ir.filmjadiid.hesabsms;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

import java.io.File;
import java.io.FileOutputStream;

/**
 * MVP safeguard for MMS push notifications. MMS decode/send is NOT IMPLEMENTED:
 * saves bounded raw WAP push data locally and warns owner. Never uploads MMS.
 * This is NOT a substitute for a complete MMS client.
 */
public class IncomingMmsReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null ||
                !"android.provider.Telephony.WAP_PUSH_DELIVER".equals(intent.getAction())) return;
        byte[] data = intent.getByteArrayExtra("data");
        if (data != null && data.length > 0 && data.length < 2_000_000) {
            File dir = new File(context.getFilesDir(), "unprocessed_mms");
            if (dir.exists() || dir.mkdirs()) {
                try (FileOutputStream out = new FileOutputStream(
                        new File(dir, "mms-" + System.currentTimeMillis() + ".wap"))) {
                    out.write(data);
                } catch (Exception e) {
                    android.util.Log.e("HesabSMS", "Cannot preserve incoming MMS PDU", e);
                }
            }
        }
        NotificationManager nm =
                (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        String channel = "hesab_mms_incomplete";
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(new NotificationChannel(
                    channel, "پیام چندرسانه‌ای", NotificationManager.IMPORTANCE_HIGH));
        }
        Intent open = new Intent(context, MessagesActivity.class);
        PendingIntent pi = PendingIntent.getActivity(context, 1, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        nm.notify(8145, new Notification.Builder(context, channel)
                .setSmallIcon(android.R.drawable.stat_notify_chat)
                .setContentTitle("MMS دریافت شد؛ پشتیبانی آزمایشی است")
                .setContentText("Hesab Messages فعلاً امکان نمایش پیوست MMS را ندارد.")
                .setAutoCancel(true).setContentIntent(pi).build());
    }
}
