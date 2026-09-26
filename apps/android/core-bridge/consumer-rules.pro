# UniFFI's generated bindings call into the native library through JNA, which finds structures and
# callbacks by reflection.
-keep class com.sun.jna.** { *; }
-keep class * implements com.sun.jna.** { *; }
-keep class uniffi.brasscribe_ffi.** { *; }
-dontwarn java.awt.**
