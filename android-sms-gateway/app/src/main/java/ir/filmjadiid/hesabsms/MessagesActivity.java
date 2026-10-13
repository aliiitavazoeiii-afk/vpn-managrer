package ir.filmjadiid.hesabsms;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.role.RoleManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Telephony;
import android.text.InputType;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.text.DateFormat;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Hesab Messages MVP: phone-local SMS inbox and conversations, manual send,
 * optional default SMS role, and a link to the existing dashboard gateway.
 * SMS bodies and personal conversations never leave the phone.
 */
public class MessagesActivity extends Activity {
    private static final int REQ_SMS_PERMISSIONS = 703;
    private final int bg = Color.rgb(9, 15, 26);
    private final int panel = Color.rgb(20, 31, 48);
    private final int accent = Color.rgb(101, 170, 255);
    private LinearLayout root;
    private ScrollView scroller;
    private String activeAddress;

    private int dp(int n) {
        return Math.round(getResources().getDisplayMetrics().density * n);
    }

    private GradientDrawable rounded(int color, int radius) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(color);
        d.setCornerRadius(dp(radius));
        return d;
    }

    private TextView label(String value, int size, int color) {
        TextView t = new TextView(this);
        t.setText(value);
        t.setTextColor(color);
        t.setTextSize(size);
        t.setGravity(Gravity.RIGHT);
        t.setTextDirection(View.TEXT_DIRECTION_RTL);
        return t;
    }

    private Button button(String value) {
        Button b = new Button(this);
        b.setText(value);
        b.setAllCaps(false);
        b.setTextSize(12);
        b.setTextColor(Color.WHITE);
        b.setBackground(rounded(Color.rgb(38, 63, 97), 12));
        b.setPadding(dp(12), dp(5), dp(12), dp(5));
        return b;
    }

    private LinearLayout vertical() {
        LinearLayout v = new LinearLayout(this);
        v.setOrientation(LinearLayout.VERTICAL);
        return v;
    }

    private LinearLayout.LayoutParams margins(int top, int bottom) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(top);
        lp.bottomMargin = dp(bottom);
        return lp;
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        scroller = new ScrollView(this);
        scroller.setFillViewport(true);
        scroller.setBackgroundColor(bg);
        root = vertical();
        root.setPadding(dp(17), dp(28), dp(17), dp(35));
        scroller.addView(root);
        setContentView(scroller);
        readIncomingIntent(getIntent());
        showInbox();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        readIncomingIntent(intent);
        showInbox();
    }

    private void readIncomingIntent(Intent intent) {
        if (intent == null || !Intent.ACTION_SENDTO.equals(intent.getAction())) return;
        Uri address = intent.getData();
        if (address == null) return;
        String target = Uri.decode(address.getSchemeSpecificPart());
        if (!TextUtils.isEmpty(target)) {
            target = target.split("[;,]")[0].trim();
            activeAddress = target;
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (root != null) {
            if (activeAddress == null) showInbox();
            else showConversation(activeAddress);
        }
    }

    private boolean defaultSms() {
        return getPackageName().equals(Telephony.Sms.getDefaultSmsPackage(this));
    }

    private void requestSmsRole() {
        new AlertDialog.Builder(this)
                .setTitle("برنامه پیش‌فرض پیامک")
                .setMessage("در نسخه آزمایشی، پیامک متنی (SMS) پشتیبانی می‌شود؛ MMS و RCS هنوز کامل نیستند. اگر MMS استفاده می‌کنی، فعلاً برنامه پیش‌فرض را تغییر نده.")
                .setNegativeButton("فعلاً نه", null)
                .setPositiveButton("ادامه", (dialog, which) -> {
                    if (Build.VERSION.SDK_INT >= 29) {
                        RoleManager role = getSystemService(RoleManager.class);
                        if (role != null && role.isRoleAvailable(RoleManager.ROLE_SMS)) {
                            startActivityForResult(
                                    role.createRequestRoleIntent(RoleManager.ROLE_SMS), 704);
                            return;
                        }
                    }
                    Intent change = new Intent(Telephony.Sms.Intents.ACTION_CHANGE_DEFAULT);
                    change.putExtra(Telephony.Sms.Intents.EXTRA_PACKAGE_NAME, getPackageName());
                    startActivityForResult(change, 704);
                }).show();
    }

    private boolean hasReadPermission() {
        return checkSelfPermission(Manifest.permission.READ_SMS)
                == PackageManager.PERMISSION_GRANTED;
    }

    private void requestReadPermission() {
        if (!hasReadPermission()) {
            requestPermissions(new String[]{
                    Manifest.permission.READ_SMS, Manifest.permission.RECEIVE_SMS,
                    Manifest.permission.SEND_SMS
            }, REQ_SMS_PERMISSIONS);
        }
    }

    private void header(String section) {
        TextView brand = label("HESAB  /  MESSAGES", 11, accent);
        brand.setTypeface(null, Typeface.BOLD);
        root.addView(brand);
        TextView name = label(section, 26, Color.WHITE);
        name.setTypeface(null, Typeface.BOLD);
        root.addView(name, margins(7, 15));
    }

    private void baseActions() {
        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.RIGHT);
        Button gateway = button("⚙ اتصال به داشبورد");
        gateway.setOnClickListener(v -> startActivity(new Intent(this, MainActivity.class)));
        bar.addView(gateway);
        Button compose = button("＋ پیام جدید");
        compose.setOnClickListener(v -> compose(null));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.leftMargin = dp(8);
        bar.addView(compose, lp);
        root.addView(bar, margins(3, 17));
    }

    private void showInbox() {
        activeAddress = null;
        root.removeAllViews();
        header("پیام‌ها");
        baseActions();
        if (!defaultSms()) {
            TextView warning = label(
                    "این نسخه آزمایشی هنوز برنامه پیش‌فرض پیامک نیست. برای مشاهده کامل پیام‌ها و دریافت مستقیم SMS می‌توانی آن را پیش‌فرض کنی؛ MMS/RCS هنوز کامل پشتیبانی نمی‌شوند.",
                    13, Color.rgb(245, 193, 137));
            warning.setPadding(dp(12), dp(12), dp(12), dp(12));
            warning.setBackground(rounded(Color.rgb(62, 43, 30), 13));
            root.addView(warning, margins(1, 10));
            Button role = button("انتخاب به‌عنوان برنامه پیش‌فرض SMS");
            role.setOnClickListener(v -> requestSmsRole());
            root.addView(role, margins(0, 15));
        }
        if (!hasReadPermission()) {
            TextView ask = label("برای نمایش پیام‌های ذخیره‌شده، اجازه خواندن SMS لازم است.", 13, Color.WHITE);
            root.addView(ask, margins(7, 12));
            Button give = button("اعطای دسترسی SMS");
            give.setOnClickListener(v -> requestReadPermission());
            root.addView(give);
            return;
        }
        LinkedHashMap<String, String[]> summaries = new LinkedHashMap<>();
        String[] columns = {
                Telephony.Sms.ADDRESS, Telephony.Sms.BODY,
                Telephony.Sms.DATE, Telephony.Sms.TYPE
        };
        try (Cursor c = getContentResolver().query(
                Telephony.Sms.CONTENT_URI, columns, null, null,
                Telephony.Sms.DATE + " DESC LIMIT 700")) {
            if (c != null) {
                while (c.moveToNext()) {
                    String phone = c.getString(0);
                    if (TextUtils.isEmpty(phone) || summaries.containsKey(phone)) continue;
                    String body = c.getString(1);
                    long date = c.getLong(2);
                    summaries.put(phone, new String[] {
                            body == null ? "" : body,
                            DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT)
                                    .format(new Date(date))
                    });
                }
            }
        } catch (Exception ex) {
            root.addView(label("خواندن پیامک‌ها ناموفق بود؛ مجوزها را بررسی کن.", 13, Color.RED));
            return;
        }

        TextView count = label("مکالمات ذخیره‌شده روی همین گوشی: " + summaries.size(), 12,
                Color.rgb(142, 161, 186));
        root.addView(count, margins(6, 8));
        if (summaries.isEmpty()) {
            root.addView(label("هنوز پیامکی در گوشی پیدا نشد.", 14, Color.WHITE));
        }
        for (Map.Entry<String, String[]> entry : summaries.entrySet()) {
            final String phone = entry.getKey();
            LinearLayout card = vertical();
            card.setPadding(dp(15), dp(13), dp(15), dp(13));
            card.setBackground(rounded(panel, 14));
            TextView who = label(phone, 15, Color.WHITE);
            who.setTypeface(null, Typeface.BOLD);
            who.setTextDirection(View.TEXT_DIRECTION_LTR);
            card.addView(who);
            String body = entry.getValue()[0];
            String preview = body.length() > 95 ? body.substring(0, 95) + "…" : body;
            card.addView(label(preview, 12, Color.rgb(177, 194, 217)), margins(6, 5));
            card.addView(label(entry.getValue()[1], 11, Color.rgb(124, 148, 176)));
            card.setOnClickListener(v -> showConversation(phone));
            root.addView(card, margins(4, 6));
        }
    }

    private void showConversation(String phone) {
        activeAddress = phone;
        root.removeAllViews();
        header(phone);
        Button back = button("← بازگشت به پیام‌ها");
        back.setOnClickListener(v -> showInbox());
        root.addView(back, margins(0, 15));

        if (!hasReadPermission()) {
            requestReadPermission();
            return;
        }
        int total = 0;
        try (Cursor c = getContentResolver().query(
                Telephony.Sms.CONTENT_URI,
                new String[]{Telephony.Sms.BODY, Telephony.Sms.DATE, Telephony.Sms.TYPE},
                Telephony.Sms.ADDRESS + "=?", new String[]{phone},
                Telephony.Sms.DATE + " DESC LIMIT 150")) {
            if (c != null) {
                // Reverse temporal order using a small in-memory collection.
                java.util.ArrayList<String[]> messages = new java.util.ArrayList<>();
                while (c.moveToNext()) {
                    messages.add(new String[]{
                            c.getString(0) == null ? "" : c.getString(0),
                            String.valueOf(c.getLong(1)),
                            String.valueOf(c.getInt(2))
                    });
                }
                total = messages.size();
                for (int i = messages.size() - 1; i >= 0; i--) {
                    String[] item = messages.get(i);
                    boolean incoming = Integer.parseInt(item[2]) == Telephony.Sms.MESSAGE_TYPE_INBOX;
                    LinearLayout box = vertical();
                    box.setPadding(dp(13), dp(10), dp(13), dp(10));
                    box.setBackground(rounded(incoming ?
                            Color.rgb(25, 40, 60) : Color.rgb(25, 68, 61), 13));
                    box.addView(label(item[0], 13, Color.WHITE));
                    box.addView(label((incoming ? "دریافتی · " : "خروجی · ") +
                            DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT)
                                    .format(new Date(Long.parseLong(item[1]))),
                            10, Color.rgb(159, 179, 197)), margins(6, 0));
                    root.addView(box, margins(3, 5));
                }
            }
        } catch (Exception ex) {
            root.addView(label("نمایش مکالمه ممکن نیست.", 13, Color.RED));
        }
        if (total == 0) root.addView(label("برای این شماره پیام قبلی پیدا نشد.", 12, Color.WHITE));
        Button send = button("＋ ارسال پیام به این شماره");
        send.setOnClickListener(v -> compose(phone));
        root.addView(send, margins(17, 6));
    }

    private void compose(String phone) {
        LinearLayout fields = vertical();
        fields.setPadding(dp(14), dp(8), dp(14), 0);
        EditText number = new EditText(this);
        number.setSingleLine(true);
        number.setHint("شماره گیرنده");
        number.setInputType(InputType.TYPE_CLASS_PHONE);
        number.setText(phone == null ? "" : phone);
        fields.addView(number);

        EditText message = new EditText(this);
        message.setHint("متن پیامک");
        message.setMinLines(3);
        message.setMaxLines(7);
        message.setTextSize(14);
        fields.addView(message, margins(8, 8));

        new AlertDialog.Builder(this)
                .setTitle("ارسال SMS دستی")
                .setView(fields)
                .setNegativeButton("انصراف", null)
                .setPositiveButton("ارسال", (dialog, which) -> {
                    try {
                        ManualSmsSender.send(this,
                                number.getText().toString().trim(),
                                message.getText().toString());
                        Toast.makeText(this,
                                "درخواست ارسال ثبت شد؛ منتظر نتیجه شبکه بمان.", Toast.LENGTH_LONG).show();
                        activeAddress = number.getText().toString().trim();
                        showConversation(activeAddress);
                    } catch (Exception ex) {
                        Toast.makeText(this,
                                "SMS ارسال نشد: مجوز، شماره یا سیم‌کارت را بررسی کن.",
                                Toast.LENGTH_LONG).show();
                    }
                }).show();
    }

    @Override
    public void onBackPressed() {
        if (activeAddress != null) showInbox();
        else super.onBackPressed();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQ_SMS_PERMISSIONS) {
            if (activeAddress == null) showInbox(); else showConversation(activeAddress);
        }
    }
}
