package ir.filmjadiid.hesabsms;

import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.telephony.SmsManager;

import java.util.ArrayList;

public final class SmsSender {
    private SmsSender() {}

    @SuppressWarnings("deprecation")
    private static SmsManager managerFor(Context c) {
        int simId = Prefs.simId(c);
        if (simId >= 0) return SmsManager.getSmsManagerForSubscriptionId(simId);
        return SmsManager.getDefault();
    }

    public static void send(Context c, long jobId, String phone, String message) {
        if (phone == null || phone.trim().isEmpty()) throw new IllegalArgumentException("empty phone");
        if (message == null || message.trim().isEmpty()) throw new IllegalArgumentException("empty message");

        SmsManager manager = managerFor(c);
        ArrayList<String> parts = manager.divideMessage(message);
        if (parts == null || parts.isEmpty()) {
            parts = new ArrayList<>();
            parts.add(message);
        }

        SmsStatusReceiver.initJob(c, jobId, parts.size());

        if (parts.size() == 1) {
            PendingIntent sent = makeIntent(c, SmsStatusReceiver.ACTION_SENT, jobId, 0, 1);
            PendingIntent delivered = makeIntent(c, SmsStatusReceiver.ACTION_DELIVERED, jobId, 0, 1);
            manager.sendTextMessage(phone, null, parts.get(0), sent, delivered);
            return;
        }

        ArrayList<PendingIntent> sentIntents = new ArrayList<>();
        ArrayList<PendingIntent> deliveryIntents = new ArrayList<>();
        for (int i = 0; i < parts.size(); i++) {
            sentIntents.add(makeIntent(c, SmsStatusReceiver.ACTION_SENT, jobId, i, parts.size()));
            deliveryIntents.add(makeIntent(c, SmsStatusReceiver.ACTION_DELIVERED, jobId, i, parts.size()));
        }
        manager.sendMultipartTextMessage(phone, null, parts, sentIntents, deliveryIntents);
    }

    private static PendingIntent makeIntent(Context c, String action, long jobId, int part, int total) {
        Intent i = new Intent(c, SmsStatusReceiver.class);
        i.setAction(action);
        i.putExtra("job_id", jobId);
        i.putExtra("part", part);
        i.putExtra("total", total);
        int type = action.equals(SmsStatusReceiver.ACTION_SENT) ? 1 : 2;
        int requestCode = (int) ((jobId % 100000L) * 100L + part * 2L + type);
        return PendingIntent.getBroadcast(
                c,
                requestCode,
                i,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
    }
}
