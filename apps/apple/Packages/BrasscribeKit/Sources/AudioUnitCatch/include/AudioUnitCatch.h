#import <AVFAudio/AVFAudio.h>

NS_ASSUME_NONNULL_BEGIN

/// Makes an AVAudioUnitEffect. AVFAudio reports an audio unit that cannot be instantiated
/// (not registered, or not sandbox-safe in a sandboxed app) by raising an Objective-C
/// exception, which Swift cannot catch; this returns nil and an NSError instead.
AVAudioUnitEffect *_Nullable BCMakeAudioUnitEffect(AudioComponentDescription description, NSError *_Nullable *_Nullable error)
    NS_SWIFT_NAME(makeAudioUnitEffect(_:_:));

NS_ASSUME_NONNULL_END
