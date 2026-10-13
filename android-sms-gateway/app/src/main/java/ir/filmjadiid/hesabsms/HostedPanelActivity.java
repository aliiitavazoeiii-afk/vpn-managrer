package ir.filmjadiid.hesabsms;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * Hesab Messages hosted UI. Only the HTML/CSS/JS presentation comes from
 * the existing authenticated admin origin. SMS is handled natively on device.
 *
 * SECURITY: No JavaScriptInterface, no exposed native SMS API to remote JS.
 * Local inbox/settings links are explicit, constant action names; the WebView
 * will only load HTTPS pages from the exact Hesab admin hostname.
 */
public class HostedPanelActivity extends Activity {
    private static final String URL = "https://hesab.filmjadiid.ir/messages/";
    private static final String HOST = "hesab.filmjadiid.ir";
    private WebView web;
    private LinearLayout root;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        root = new LinearLayout(this);
        root.setBackgroundColor(Color.rgb(8, 15, 30));
        root.setOrientation(LinearLayout.VERTICAL);
        setContentView(root);

        LinearLayout bar = new LinearLayout(this);
        bar.setPadding(12, 14, 12, 9);
        bar.setBackgroundColor(Color.rgb(14, 25, 43));
        Button inbox = button("✉ پیام‌های گوشی");
        inbox.setOnClickListener(v -> openLocalInbox());
        bar.addView(inbox, new LinearLayout.LayoutParams(0, 54, 1f));
        Button settings = button("⚙ تنظیمات و اتصال");
        settings.setOnClickListener(v -> openSettings());
        LinearLayout.LayoutParams settingParams = new LinearLayout.LayoutParams(0, 54, 1f);
        settingParams.leftMargin = 10;
        bar.addView(settings, settingParams);
        root.addView(bar);

        web = new WebView(this);
        WebSettings options = web.getSettings();
        options.setJavaScriptEnabled(true);
        options.setDomStorageEnabled(true);
        options.setAllowFileAccess(false);
        options.setAllowContentAccess(false);
        options.setJavaScriptCanOpenWindowsAutomatically(false);
        options.setSupportMultipleWindows(false);
        options.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        if (android.os.Build.VERSION.SDK_INT >= 26) options.setSafeBrowsingEnabled(true);
        options.setUserAgentString(options.getUserAgentString() + " HesabNative/2");
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return intercept(request.getUrl());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String value) {
                return intercept(Uri.parse(value));
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request,
                                        android.webkit.WebResourceError error) {
                if (request.isForMainFrame()) showNetworkHint();
            }
        });
        root.addView(web, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        web.loadUrl(URL);
    }

    private Button button(String s) {
        Button b = new Button(this);
        b.setText(s);
        b.setAllCaps(false);
        b.setTextSize(12);
        b.setTextColor(Color.WHITE);
        b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.rgb(34, 55, 87)));
        return b;
    }

    private boolean intercept(Uri uri) {
        if (uri == null) return true;
        String scheme = uri.getScheme();
        String host = uri.getHost();
        if ("hesab".equals(scheme) && "local".equals(host)) {
            if ("/inbox".equals(uri.getPath())) openLocalInbox();
            else if ("/settings".equals(uri.getPath())) openSettings();
            return true;
        }
        if ("https".equalsIgnoreCase(scheme) && HOST.equalsIgnoreCase(host)
                && (uri.getPort() == -1 || uri.getPort() == 443)) {
            return false; // Only this exact HTTPS origin stays in our WebView.
        }
        if ("https".equalsIgnoreCase(scheme)) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, uri));
            } catch (ActivityNotFoundException ignored) {}
        }
        return true; // Never load cleartext, file://, intent:// or external hosts.
    }

    private void openLocalInbox() {
        startActivity(new Intent(this, MessagesActivity.class));
    }

    private void openSettings() {
        startActivity(new Intent(this, MainActivity.class));
    }

    private void showNetworkHint() {
        if (root == null || isFinishing()) return;
        TextView hint = new TextView(this);
        hint.setText("اتصال به سرور حساب برقرار نیست. پیامک‌های گوشی همچنان از بخش محلی در دسترس هستند.");
        hint.setTextColor(Color.rgb(255, 208, 159));
        hint.setTextSize(12);
        hint.setPadding(20, 12, 20, 12);
        hint.setTextDirection(View.TEXT_DIRECTION_RTL);
        root.addView(hint, 1);
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            root.removeView(web);
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }
}
