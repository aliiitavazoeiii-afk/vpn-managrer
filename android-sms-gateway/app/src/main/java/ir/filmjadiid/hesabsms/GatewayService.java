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

public class GatewayService extends Service {
    public static final String ACTION_START = "ir.filmjadiid.hesabsms.START";
    public static final String ACTION_STOP = "ir.filmjadiid.hesabsms.STOP";

    private static final String CHANNEL_ID = "hesab_sms_gateway";
    private static final int NOTIFICATION_ID = 4107;

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
        startForeground(NOTIFICATION_ID, notification("در حال اتصال به حساب…"));
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
                    SmsStatusReceiver.flushPending(this);

                    long now = System.currentTimeMillis();
                    if (now - lastHeartbeat > 60000L) {
                        boolean hb = ApiClient.heartbeat(this);
                        updateNotification(hb ? "متصل · در انتظار پیام" : "اتصال به سرور برقرار نیست");
                        if (hb) lastHeartbeat = now;
                    }

                    ApiClient.SmsJob job = ApiClient.poll(this);
                    if (job != null) {
                        int simId = Prefs.simId(this);
                        boolean accepted = ApiClient.reportStatus(this, job.id, "dispatching", "", simId);
                        if (accepted) {
                            updateNotification("در حال ارسال به " + job.phone);
                            try {
                                SmsSender.send(this, job.id, job.phone, job.message);
                            } catch (Exception e) {
                                ApiClient.reportStatus(this, job.id, "failed", e.getClass().getSimpleName() + ": " + e.getMessage(), simId);
                            }
                        }
                    }
                } catch (Exception e) {
                    updateNotification("خطای ارتباط · تلاش مجدد");
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
                CHANNEL_ID,
                "Hesab SMS Gateway",
                NotificationManager.IMPORTANCE_LOW
        );
        ch.setDescription("Keeps the personal SIM SMS gateway connected");
        getSystemService(NotificationManager.class).createNotificationChannel(ch);
    }

    private Notification notification(String text) {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(
                this,
                0,
                open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        return new Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("Hesab SMS Gateway")
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
