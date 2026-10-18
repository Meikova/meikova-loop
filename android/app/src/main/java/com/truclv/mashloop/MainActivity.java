package com.truclv.mashloop;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.media.AudioManager;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    private AudioManager audioManager;
    private BroadcastReceiver volumeReceiver;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        audioManager = (AudioManager) getSystemService(Context.AUDIO_SERVICE);

        // Allow web slider to set Android media volume
        WebView webView = getBridge().getWebView();
        if (webView != null) {
            webView.addJavascriptInterface(new Object() {
                @JavascriptInterface
                public void setVolume(float ratio) {
                    if (audioManager != null) {
                        int max = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
                        int target = Math.round(ratio * max);
                        audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, target, 0);
                    }
                }

                @JavascriptInterface
                public float getVolume() {
                    if (audioManager != null) {
                        int cur = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC);
                        int max = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
                        return max > 0 ? (float) cur / (float) max : 1.0f;
                    }
                    return 1.0f;
                }
            }, "AndroidAudio");
        }

        // Listen for hardware volume button presses on Android
        volumeReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                if ("android.media.VOLUME_CHANGED_ACTION".equals(intent.getAction())) {
                    notifyVolumeToWeb();
                }
            }
        };
        try {
            registerReceiver(volumeReceiver, new IntentFilter("android.media.VOLUME_CHANGED_ACTION"));
        } catch (Exception ignored) {}
    }

    private void notifyVolumeToWeb() {
        if (audioManager == null) return;
        int cur = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC);
        int max = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
        final float ratio = max > 0 ? (float) cur / (float) max : 1.0f;
        runOnUiThread(() -> {
            if (getBridge() != null && getBridge().getWebView() != null) {
                getBridge().getWebView().evaluateJavascript(
                    "window.__onSystemVolume && window.__onSystemVolume(" + ratio + ");",
                    null
                );
            }
        });
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        if (volumeReceiver != null) {
            try {
                unregisterReceiver(volumeReceiver);
            } catch (Exception ignored) {}
        }
    }
}
