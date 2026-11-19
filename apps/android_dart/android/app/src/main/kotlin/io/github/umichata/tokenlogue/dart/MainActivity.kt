package io.github.umichata.tokenlogue.dart

import android.app.KeyguardManager
import android.hardware.biometrics.BiometricManager
import android.hardware.biometrics.BiometricPrompt
import android.os.Build
import android.os.CancellationSignal
import android.os.SystemClock
import android.provider.Settings
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class MainActivity : FlutterActivity() {
    private val alias = "io.github.umichata.tokenlogue.dart.vault.v1"
    private val vault by lazy { getSharedPreferences(alias, MODE_PRIVATE) }

    private fun key(create: Boolean): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val existing = store.getKey(alias, null)
        if (existing is SecretKey) return existing
        check(create && !vault.contains("profile"))
        val spec = KeyGenParameterSpec.Builder(alias,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256).build()
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            .apply { init(spec) }.generateKey()
    }

    private fun read(): ByteArray? {
        val packed = vault.getString("profile", null) ?: return null
        val bytes = Base64.decode(packed, Base64.NO_WRAP)
        require(bytes.size >= 28)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(false), GCMParameterSpec(128, bytes.copyOfRange(0,12)))
        cipher.updateAAD(alias.toByteArray(Charsets.UTF_8))
        return cipher.doFinal(bytes, 12, bytes.size - 12)
    }

    private fun write(value: ByteArray) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key(true))
        cipher.updateAAD(alias.toByteArray(Charsets.UTF_8))
        val bytes = cipher.iv + cipher.doFinal(value)
        require(cipher.iv.size == 12)
        check(vault.edit().putString("profile", Base64.encodeToString(bytes, Base64.NO_WRAP)).commit())
    }

    private var promptCancellation: CancellationSignal? = null
    private var promptReply: MethodChannel.Result? = null

    private fun stopPrompt() {
        val result = promptReply
        promptReply = null
        val signal = promptCancellation
        promptCancellation = null
        signal?.cancel()
        result?.success(false)
    }

    override fun onStop() { stopPrompt(); super.onStop() }
    override fun onDestroy() { stopPrompt(); super.onDestroy() }

    private fun canRecover(): Boolean {
        if (Build.VERSION.SDK_INT < 30) return false
        return getSystemService(KeyguardManager::class.java).isDeviceSecure &&
            getSystemService(BiometricManager::class.java).canAuthenticate(
                BiometricManager.Authenticators.DEVICE_CREDENTIAL or
                    BiometricManager.Authenticators.BIOMETRIC_STRONG) == BiometricManager.BIOMETRIC_SUCCESS
    }

    private fun authenticate(title: String, result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < 30 || !canRecover() || promptReply != null) {
            result.success(false)
            return
        }
        val signal = CancellationSignal()
        val prompt = BiometricPrompt.Builder(this)
            .setTitle(title)
            .setAllowedAuthenticators(BiometricManager.Authenticators.DEVICE_CREDENTIAL or
                BiometricManager.Authenticators.BIOMETRIC_STRONG)
            .build()
        promptCancellation = signal
        promptReply = result
        try {
            prompt.authenticate(signal, mainExecutor, object : BiometricPrompt.AuthenticationCallback() {
                private fun complete(ok: Boolean) {
                    if (promptReply !== result) return
                    promptReply = null
                    promptCancellation = null
                    result.success(ok)
                }
                override fun onAuthenticationSucceeded(value: BiometricPrompt.AuthenticationResult) = complete(true)
                override fun onAuthenticationError(error: Int, reason: CharSequence) = complete(false)
            })
        } catch (_: Exception) { stopPrompt() }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "$alias/platform").setMethodCallHandler { call, result ->
            try {
                when (call.method) {
                    "recoveryAvailable" -> result.success(canRecover())
                    "authenticateDevice" -> authenticate(requireNotNull(call.arguments as? String), result)
                    "cancelDevice" -> { stopPrompt(); result.success(null) }
                    "language" -> result.success(vault.getString("language", null))
                    "setLanguage" -> {
                        val language = call.arguments as? String
                        require(language == "ru" || language == "en")
                        check(vault.edit().putString("language", language).commit())
                        result.success(null)
                    }
                    "deleting" -> result.success(vault.getBoolean("deleting", false))
                    "beginDelete" -> {
                        check(vault.edit().putBoolean("deleting", true).commit())
                        result.success(null)
                    }
                    "finishDelete" -> {
                        check(vault.getBoolean("deleting", false))
                        KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry(alias) }
                        check(vault.edit().clear().commit())
                        result.success(null)
                    }
                    "read" -> result.success(read())
                    "write" -> { write(requireNotNull(call.arguments as? ByteArray)); result.success(null) }
                    "clock" -> result.success(listOf(SystemClock.elapsedRealtime(),
                        Settings.Global.getInt(contentResolver, Settings.Global.BOOT_COUNT, -1)))
                    else -> result.notImplemented()
                }
            } catch (_: Exception) { result.error("storage_unavailable", null, null) }
        }
    }
}
