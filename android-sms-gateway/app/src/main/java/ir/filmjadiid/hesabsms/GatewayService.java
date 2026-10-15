package ir.filmjadiid.hesabsms;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.IBinder;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Fail-closed SMS V2 worker. NEVER calls the legacy V1 queue.
 * A job is persisted locally before invoking the modem; ambiguous results
 * stop the queue and are never retried automatically.
 */
public class GatewayService extends Service {
    public static final String ACTION_START = "ir.filmjadiid.hesabsms.START";
    public static final String ACTION_STOP = "ir.filmjadiid.hesabsms.STOP";

    private static final String CHANNEL_ID = "hesab_sms_gateway";
    private static final int NOTIFICATION_ID = 4107;
    private static final long CALLBACK_WATCHDOG_MS = 8L * 60L * 1000L;

    private volatile boolean running = false;
    private ExecutorService worker;

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            Prefs.setEnabled(this, false);
            stopGateway();
            return START_NOT_STICKY;
        }

        Prefs.setEnabled(this, true);
        startForeground(NOTIFICATION_ID, notification("حالت آزمایشی · بررسی اتصال"));
        startWorker();
        return START_STICKY;
    }

    private synchronized void startWorker() {
        if (running) return;
        running = true;
        worker = Executors.newSingleThreadExecutor();
        worker.submit(() -> {
            long lastHeartbeat = 0L;
            while (running && Prefs.enabled(this)) {
                try {
                    // Receipts were written to disk by the Android receiver.
                    // Retry the *report*, not the outgoing SMS.
                    SmsStatusReceiver.flushPending(this);

                    long now = System.currentTimeMillis();
                    if (now - lastHeartbeat > 60000L) {
                        boolean hb = ApiClient.heartbeat(this);
                        updateNotification(hb ? "متصل · حالت آزمایشی" : "اتصال به API نسخه ۲ برقرار نیست");
                        if (hb) lastHeartbeat = now;
                    }

                    if (Prefs.paused(this)) {
                        updateNotification("ارسال متوقف است · نیاز به بررسی");
                    } else if (Prefs.inFlight(this) >= 0L) {
                        long id = Prefs.inFlight(this);
                        long started = Prefs.inFlightAt(this);
                        if (started > 0 && now - started > CALLBACK_WATCHDOG_MS) {
                            // No automatic retry, even after process death.
                            SmsStatusReceiver.reportUnknown(this, id,
                                    "SMS callback or server acknowledgement timed out");
                            updateNotification("نتیجه پیامک نامشخص است · ارسال متوقف");
                        } else {
                            updateNotification("منتظر نتیجه پیامک شماره " + id);
                        }
                    } else if (!Prefs.validTestPhone(Prefs.testPhone(this))) {
                        updateNotification("شماره آزمایشی ۱۱ رقمی ثبت نشده");
                    } else if (Prefs.simId(this) < 0) {
                        updateNotification("سیم‌کارت ارسال را صریحاً انتخاب کن");
                    } else if (now >= Prefs.nextAllowed(this)) {
                        // The V2 server must filter by test_phone BEFORE claiming.
                        ApiClient.SmsJob job = ApiClient.poll(this);
                        if (job != null) dispatchTestJob(job);
                    } else {
                        updateNotification("فاصله ایمنی بین پیامک‌ها");
                    }
                } catch (Exception e) {
                    updateNotification("خطای اتصال/پردازش · بدون ارسال دوباره");
                }

                try {
                    Thread.sleep(Prefs.pollSeconds(this) * 1000L);
                } catch (InterruptedException ignored) {
                    break;
                }
            }
            running = false;
        });
    }

    private void dispatchTestJob(ApiClient.SmsJob job) {
        // Never start an SMS to an unapproved recipient, even if the server
        // is running old code which ignored the test_phone query parameter.
        if (!Prefs.allowedTestRecipient(this, job.phone)) {
            Prefs.pause(this, "Server returned unapproved recipient; claimed job "
                    + job.id + "; NO SMS submitted");
            updateNotification("شماره غیرمجاز · ارسال متوقف");
            return;
        }
        if (!Prefs.begin(this, job.id)) {
            Prefs.pause(this, "Cannot persist active job " + job.id);
            updateNotification("ثبت امن تلاش انجام نشد · توقف");
            return;
        }

        boolean acceptedStart = false;
        try {
            int parts = SmsSender.partsCount(this, job.message);
            if (parts < 1 || parts > 30) {
                Prefs.pause(this, "Invalid SMS part count for job " + job.id);
                return;
            }
            if (!ApiClient.markAttempting(this, job.id, parts)) {
                // HTTP could have succeeded remotely despite a lost response.
                // Remain locked and require manual reconciliation.
                Prefs.pause(this, "V2 /start not acknowledged for job " + job.id
                        + "; NO automatic retry");
                updateNotification("شروع ارسال تأیید نشد · توقف امن");
                return;
            }
            acceptedStart = true;
            updateNotification("ارسال آزمایشی · job " + job.id);
            SmsSender.send(this, job.id, job.phone, job.message);
        } catch (Exception e) {
            if (acceptedStart) {
                // SmsManager may have accepted the SMS before throwing.
                SmsStatusReceiver.reportUnknown(this, job.id,
                        "Send exception: " + e.getClass().getSimpleName());
            } else {
                Prefs.pause(this, "Preparation failed for job " + job.id
                        + ": " + e.getClass().getSimpleName());
            }
            updateNotification("ارسال متوقف · بررسی وضعیت پیامک");
        }
    }

    private void stopGateway() {
        running = false;
        if (worker != null) worker.shutdownNow();
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    @Override
    public void onDestroy() {
        running = false;
        if (worker != null) worker.shutdownNow();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createChannel() {
        NotificationChannel ch = new NotificationChannel(
                CHANNEL_ID, "Hesab SMS Gateway", NotificationManager.IMPORTANCE_LOW);
        ch.setDescription("Personal SIM SMS test gateway; safety-paused on uncertain outcomes");
        getSystemService(NotificationManager.class).createNotificationChannel(ch);
    }

    private Notification notification(String text) {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(
                this, 0, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("Hesab SMS Gateway · TEST ONLY")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_notify_chat)
                .setContentIntent(pi)
                .setOngoing(true)
                .build();
    }

    private void updateNotification(String text) {
        getSystemService(NotificationManager.class).notify(NOTIFICATION_ID, notification(text));
    }
}
