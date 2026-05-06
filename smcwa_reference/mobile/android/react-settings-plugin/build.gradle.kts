plugins {
    id("java-gradle-plugin")
}

repositories {
    google()
    mavenCentral()
}

gradlePlugin {
    plugins {
        create("reactSettingsPlugin") {
            id = "com.facebook.react.settings"
            implementationClass = "expo.plugins.ReactSettingsPlugin"
        }
    }
}

java {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
}
