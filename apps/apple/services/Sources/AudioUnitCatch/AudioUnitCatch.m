#import "AudioUnitCatch.h"

AVAudioUnitEffect *BCMakeAudioUnitEffect(AudioComponentDescription description, NSError **error) {
    @try {
        return [[AVAudioUnitEffect alloc] initWithAudioComponentDescription:description];
    } @catch (NSException *exception) {
        if (error) {
            *error = [NSError errorWithDomain:exception.name code:0 userInfo:@{
                NSLocalizedDescriptionKey: exception.reason ?: exception.name,
            }];
        }
        return nil;
    }
}
