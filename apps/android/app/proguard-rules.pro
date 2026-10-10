# alphaTab builds its settings and model by reflection-free generated code, but its JSON serializers and
# worker entry points are referenced by name.
-keep class alphaTab.** { *; }
-dontwarn alphaTab.**

# kotlinx.serialization: keep generated serializers of the app's and libraries' @Serializable classes.
-keepclassmembers class no.brasscribe.** {
    *** Companion;
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class no.brasscribe.**$$serializer { *; }

# Ktor and OkHttp reference optional platform classes.
-dontwarn org.slf4j.**
-dontwarn java.lang.management.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
