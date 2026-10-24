# Brasscribe only: Fretscribe has no ONNX Runtime.
# ONNX Runtime calls back into its Java classes from JNI.
-keep class ai.onnxruntime.** { *; }
