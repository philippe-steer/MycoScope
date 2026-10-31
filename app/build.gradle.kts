plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "fr.mycoscope"
    compileSdk = 35

    defaultConfig {
        applicationId = "fr.mycoscope"
        minSdk = 26
        targetSdk = 34
        versionCode = 6
        versionName = "0.1.5"
        // Couches environnementales (PMTiles) : release « data-v1 » du dépôt GitHub
        buildConfigField("String", "DATA_URL",
            "\"https://github.com/philippe-steer/MycoScope/releases/download/data-v1/france.pmtiles\"")
    }

    val ksFile = System.getenv("MS_KEYSTORE")?.takeIf { file(it).exists() }
    signingConfigs {
        if (ksFile != null) {
            create("personal") {
                storeFile = file(ksFile)
                storePassword = System.getenv("MS_STORE_PASS")
                keyAlias = System.getenv("MS_KEY_ALIAS")
                keyPassword = System.getenv("MS_KEY_PASS")
            }
        }
    }

    buildTypes {
        debug {
            if (ksFile != null) signingConfig = signingConfigs.getByName("personal")
        }
        release {
            isMinifyEnabled = false
            signingConfig = if (ksFile != null) signingConfigs.getByName("personal") else null
        }
    }

    dependenciesInfo {
        includeInApk = false
        includeInBundle = false
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-core")

    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    implementation("org.osmdroid:osmdroid-android:6.1.20")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
