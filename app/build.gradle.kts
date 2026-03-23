import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

val localProps = Properties().apply {
    val f = rootProject.file("local.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

// Auto-version from git commit count
val gitVersionCode: Int by lazy {
    try {
        val process = ProcessBuilder("git", "rev-list", "--count", "HEAD")
            .directory(rootProject.projectDir)
            .start()
        process.inputStream.bufferedReader().readText().trim().toInt()
    } catch (_: Exception) {
        1
    }
}

val gitVersionName: String by lazy {
    try {
        val count = gitVersionCode
        "1.0.${count}"
    } catch (_: Exception) {
        "1.0.0"
    }
}

android {
    namespace = "com.boxbuilder.workplanner"
    compileSdk {
        version = release(36)
    }

    signingConfigs {
        create("release") {
            val ksPath = System.getenv("RELEASE_KEYSTORE_PATH")
                ?: rootProject.file("workplanner-release.jks").takeIf { it.exists() }?.absolutePath
            if (ksPath != null) {
                storeFile = file(ksPath)
                storePassword = System.getenv("RELEASE_KEYSTORE_PASSWORD") ?: "workplanner2026"
                keyAlias = System.getenv("RELEASE_KEY_ALIAS") ?: "workplanner"
                keyPassword = System.getenv("RELEASE_KEY_PASSWORD") ?: "workplanner2026"
            }
        }
    }

    defaultConfig {
        applicationId = "com.boxbuilder.workplanner"
        minSdk = 24
        targetSdk = 36
        versionCode = gitVersionCode
        versionName = gitVersionName

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        buildConfigField("String", "GOOGLE_CLIENT_ID",
            "\"${localProps.getProperty("GOOGLE_CLIENT_ID", "")}\"")
        buildConfigField("String", "API_BASE_URL",
            "\"${localProps.getProperty("API_BASE_URL", "http://10.0.2.2:8080")}\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    kotlinOptions {
        jvmTarget = "11"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    // Core
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)

    // Compose
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.activity.compose)
    debugImplementation(libs.androidx.compose.ui.tooling)

    // Networking
    implementation(libs.retrofit)
    implementation(libs.retrofit.converter.gson)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging.interceptor)

    // Hilt
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.androidx.hilt.navigation.compose)

    // Navigation
    implementation(libs.androidx.navigation.compose)

    // Lifecycle
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)

    // Coroutines
    implementation(libs.kotlinx.coroutines.android)

    // Credential Manager (Google Sign-In)
    implementation(libs.androidx.credentials)
    implementation(libs.androidx.credentials.play.services.auth)
    implementation(libs.googleid)
    implementation(libs.play.services.auth)

    // Testing
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
}
