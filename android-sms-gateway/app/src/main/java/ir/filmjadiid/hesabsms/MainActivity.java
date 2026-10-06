package ir.filmjadiid.hesabsms;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.telephony.SubscriptionInfo;
import android.telephony.SubscriptionManager;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;

public class MainActivity extends Activity {
    private static final int REQ_PERMS = 701;

    private EditText baseUrl;
    private EditText token;
    private EditText deviceName;
    private EditText pollSeconds;
    private Spinner simSpinner;
    private TextView status;
    private final ArrayList<Integer> simIds = new ArrayList<>();

    private int dp(int n) {
        return Math.round(n * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(Color.rgb(8, 13, 22));

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(28), dp(20), dp(32));
        scroll.addView(root, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        TextView kicker = text("HESAB  •  PERSONAL SMS GATEWAY", 11, Color.rgb(125, 170, 255));
        kicker.setLetterSpacing(.10f);
        root.addView(kicker);

        TextView title = text("ارسال پیامک از خط خودت", 27, Color.WHITE);
        title.setGravity(Gravity.RIGHT);
        title.setPadding(0, dp(10), 0, dp(4));
        root.addView(title);

        TextView intro = text(
                "سایت درخواست را در صف می‌گذارد؛ این گوشی آن را می‌گیرد و مستقیماً با سیم‌کارت انتخابی SMS می‌فرستد.",
                13,
                Color.rgb(145, 156, 174)
        );
        intro.setGravity(Gravity.RIGHT);
        intro.setLineSpacing(0, 1.35f);
        root.addView(intro);

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(16), dp(16), dp(16));
        LinearLayout.LayoutParams cardLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        cardLp.topMargin = dp(22);
        card.setBackground(roundRect(Color.rgb(15, 23, 36), Color.rgb(35, 48, 67), 18));
        root.addView(card, cardLp);

        addLabel(card, "آدرس سرور");
        baseUrl = input(Prefs.baseUrl(this), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        baseUrl.setTextDirection(View.TEXT_DIRECTION_LTR);
        card.addView(baseUrl);

        addLabel(card, "Gateway Token");
        token = input(Prefs.token(this), InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        token.setTextDirection(View.TEXT_DIRECTION_LTR);
        card.addView(token);

        addLabel(card, "نام این گوشی");
        deviceName = input(Prefs.deviceName(this), InputType.TYPE_CLASS_TEXT);
        card.addView(deviceName);

        addLabel(card, "سیم‌کارت ارسال");
        simSpinner = new Spinner(this);
        simSpinner.setPadding(dp(8), dp(3), dp(8), dp(3));
        LinearLayout.LayoutParams spinnerLp = fieldLp();
        card.addView(simSpinner, spinnerLp);

        addLabel(card, "فاصله بررسی صف (ثانیه)");
        pollSeconds = input(String.valueOf(Prefs.pollSeconds(this)), InputType.TYPE_CLASS_NUMBER);
        card.addView(pollSeconds);

        status = text("", 12, Color.rgb(170, 180, 195));
        status.setGravity(Gravity.RIGHT);
        LinearLayout.LayoutParams statusLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        statusLp.topMargin = dp(14);
        card.addView(status, statusLp);

        Button start = button("شروع Gateway", Color.rgb(235, 240, 247), Color.rgb(15, 23, 36));
        LinearLayout.LayoutParams buttonLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(48)
        );
        buttonLp.topMargin = dp(16);
        card.addView(start, buttonLp);

        Button stop = button("توقف Gateway", Color.rgb(35, 45, 61), Color.rgb(235, 240, 247));
        LinearLayout.LayoutParams stopLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(46)
        );
        stopLp.topMargin = dp(9);
        card.addView(stop, stopLp);

        Button test = button("تست اتصال به سایت", Color.rgb(20, 43, 75), Color.rgb(174, 205, 255));
        LinearLayout.LayoutParams testLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(46)
        );
        testLp.topMargin = dp(9);
        card.addView(test, testLp);

        Button battery = button("اجازه فعالیت دائمی در پس‌زمینه", Color.rgb(31, 39, 53), Color.rgb(196, 205, 220));
        LinearLayout.LayoutParams batteryLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(46)
        );
        batteryLp.topMargin = dp(9);
        card.addView(battery, batteryLp);

        TextView note = text(
                "برای ارسال خودکار، مجوز SMS و Phone را تأیید کن. اعلان دائمی کوچک یعنی Gateway روشن است. پیام‌ها با SmsManager از سیم‌کارت خود گوشی ارسال می‌شوند.",
                11,
                Color.rgb(110, 124, 145)
        );
        note.setGravity(Gravity.RIGHT);
        note.setLineSpacing(0, 1.4f);
        LinearLayout.LayoutParams noteLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        noteLp.topMargin = dp(18);
        root.addView(note, noteLp);

        start.setOnClickListener(v -> startGateway());
        stop.setOnClickListener(v -> stopGateway());
        test.setOnClickListener(v -> testConnection());
        battery.setOnClickListener(v -> requestBatteryExemption());

        ensurePermissions(false);
        loadSims();
        refreshStatus();
        setContentView(scroll);
    }

    private void addLabel(LinearLayout parent, String s) {
        TextView label = text(s, 11, Color.rgb(132, 145, 164));
        label.setGravity(Gravity.RIGHT);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        lp.topMargin = dp(13);
        lp.bottomMargin = dp(6);
        parent.addView(label, lp);
    }

    private EditText input(String value, int type) {
        EditText e = new EditText(this);
        e.setText(value);
        e.setTextColor(Color.WHITE);
        e.setHintTextColor(Color.rgb(95, 108, 128));
        e.setTextSize(13);
        e.setSingleLine(true);
        e.setInputType(type);
        e.setPadding(dp(12), 0, dp(12), 0);
        e.setBackground(roundRect(Color.rgb(9, 15, 25), Color.rgb(42, 55, 74), 11));
        e.setLayoutParams(fieldLp());
        return e;
    }

    private LinearLayout.LayoutParams fieldLp() {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(46)
        );
        return lp;
    }

    private TextView text(String s, int sp, int color) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        return t;
    }

    private Button button(String s, int bg, int fg) {
        Button b = new Button(this);
        b.setText(s);
        b.setAllCaps(false);
        b.setTextSize(12);
        b.setTextColor(fg);
        b.setBackground(roundRect(bg, bg, 12));
        return b;
    }

    private GradientDrawable roundRect(int fill, int stroke, int radiusDp) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(fill);
        g.setCornerRadius(dp(radiusDp));
        g.setStroke(dp(1), stroke);
        return g;
    }

    private boolean hasCorePermissions() {
        return checkSelfPermission(Manifest.permission.SEND_SMS) == PackageManager.PERMISSION_GRANTED
                && checkSelfPermission(Manifest.permission.READ_PHONE_STATE) == PackageManager.PERMISSION_GRANTED;
    }

    private void ensurePermissions(boolean force) {
        ArrayList<String> needed = new ArrayList<>();
        if (checkSelfPermission(Manifest.permission.SEND_SMS) != PackageManager.PERMISSION_GRANTED)
            needed.add(Manifest.permission.SEND_SMS);
        if (checkSelfPermission(Manifest.permission.READ_PHONE_STATE) != PackageManager.PERMISSION_GRANTED)
            needed.add(Manifest.permission.READ_PHONE_STATE);
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            needed.add(Manifest.permission.POST_NOTIFICATIONS);

        if (!needed.isEmpty() && force) {
            requestPermissions(needed.toArray(new String[0]), REQ_PERMS);
        }
    }

    private void saveSettings() {
        Prefs.setBaseUrl(this, baseUrl.getText().toString());
        Prefs.setToken(this, token.getText().toString());
        Prefs.setDeviceName(this, deviceName.getText().toString());

        int seconds = 15;
        try { seconds = Integer.parseInt(pollSeconds.getText().toString().trim()); }
        catch (Exception ignored) {}
        Prefs.setPollSeconds(this, seconds);

        int pos = simSpinner.getSelectedItemPosition();
        int simId = pos >= 0 && pos < simIds.size() ? simIds.get(pos) : -1;
        Prefs.setSimId(this, simId);
    }

    private void startGateway() {
        String url = baseUrl.getText().toString().trim();
        String tok = token.getText().toString().trim();
        if (!url.startsWith("https://")) {
            toast("آدرس باید با https:// شروع شود.");
            return;
        }
        if (tok.length() < 24) {
            toast("Gateway Token را از سرور وارد کن.");
            return;
        }
        if (!hasCorePermissions()) {
            ensurePermissions(true);
            toast("مجوزها را تأیید کن و دوباره «شروع Gateway» را بزن.");
            return;
        }

        saveSettings();
        Prefs.setEnabled(this, true);
        Intent i = new Intent(this, GatewayService.class).setAction(GatewayService.ACTION_START);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(i);
        else startService(i);
        refreshStatus();
        toast("Gateway روشن شد.");
    }

    private void stopGateway() {
        Prefs.setEnabled(this, false);
        Intent i = new Intent(this, GatewayService.class).setAction(GatewayService.ACTION_STOP);
        startService(i);
        stopService(new Intent(this, GatewayService.class));
        refreshStatus();
        toast("Gateway متوقف شد.");
    }

    private void testConnection() {
        saveSettings();
        status.setText("در حال تست اتصال…");
        new Thread(() -> {
            boolean ok = ApiClient.ping(this);
            if (ok && Prefs.token(this).length() >= 24) ok = ApiClient.heartbeat(this);
            final boolean result = ok;
            runOnUiThread(() -> {
                status.setText(result
                        ? "● اتصال به hesab.filmjadiid.ir برقرار است"
                        : "● اتصال برقرار نشد؛ آدرس، Token و مسیر سرور را بررسی کن");
                status.setTextColor(result ? Color.rgb(94, 219, 132) : Color.rgb(248, 113, 113));
            });
        }, "gateway-test").start();
    }

    @SuppressWarnings("deprecation")
    private void loadSims() {
        ArrayList<String> labels = new ArrayList<>();
        simIds.clear();
        labels.add("SIM پیش‌فرض گوشی");
        simIds.add(-1);

        if (checkSelfPermission(Manifest.permission.READ_PHONE_STATE) == PackageManager.PERMISSION_GRANTED) {
            try {
                SubscriptionManager sm = getSystemService(SubscriptionManager.class);
                List<SubscriptionInfo> infos = sm.getActiveSubscriptionInfoList();
                if (infos != null) {
                    for (SubscriptionInfo info : infos) {
                        String carrier = info.getCarrierName() == null ? "SIM" : info.getCarrierName().toString();
                        labels.add("SIM " + (info.getSimSlotIndex() + 1) + " · " + carrier);
                        simIds.add(info.getSubscriptionId());
                    }
                }
            } catch (Exception ignored) {}
        }

        ArrayAdapter<String> adapter = new ArrayAdapter<>(
                this,
                android.R.layout.simple_spinner_item,
                labels
        );
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        simSpinner.setAdapter(adapter);

        int saved = Prefs.simId(this);
        int index = simIds.indexOf(saved);
        if (index >= 0) simSpinner.setSelection(index);
    }

    private void requestBatteryExemption() {
        try {
            PowerManager pm = getSystemService(PowerManager.class);
            if (pm.isIgnoringBatteryOptimizations(getPackageName())) {
                toast("Battery optimization برای این اپ غیرفعال است.");
                return;
            }
            Intent i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
            i.setData(Uri.parse("package:" + getPackageName()));
            startActivity(i);
        } catch (Exception e) {
            startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
        }
    }

    private void refreshStatus() {
        if (status == null) return;
        boolean on = Prefs.enabled(this);
        status.setText(on
                ? "● Gateway فعال است · Device ID: " + Prefs.deviceId(this)
                : "● Gateway خاموش است · تنظیمات را وارد و Start کن");
        status.setTextColor(on ? Color.rgb(94, 219, 132) : Color.rgb(148, 163, 184));
    }

    private void toast(String s) {
        Toast.makeText(this, s, Toast.LENGTH_LONG).show();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (simSpinner != null) loadSims();
        refreshStatus();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQ_PERMS) {
            loadSims();
            refreshStatus();
        }
    }
}
