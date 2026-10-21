"""Memory-bounded Whisper features, preserving its complete timestamp grid."""

import numpy as np


class BoundedFeatureExtractor:
    """Delegate songs unchanged; batch spectral temporaries for long programs.

    Retains the full mel output (about 0.46 GB for four hours / 80 bands),
    but never creates an hours-long windowed PCM or complex spectrogram.
    Normalization uses the global maximum just like faster-whisper.
    """

    def __init__(self, delegate, threshold_seconds=600, batch_frames=4096):
        self.delegate = delegate
        self.threshold_seconds = threshold_seconds
        self.batch_frames = batch_frames

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def __call__(self, waveform, padding=160, chunk_length=None):
        if len(waveform) <= self.sampling_rate * self.threshold_seconds:
            return self.delegate(waveform, padding=padding, chunk_length=chunk_length)
        if chunk_length is not None:
            self.delegate.n_samples = chunk_length * self.sampling_rate
            self.delegate.nb_max_frames = self.n_samples // self.hop_length
        samples = np.asarray(waveform, dtype=np.float32)
        if padding:
            samples = np.pad(samples, (0, padding))
        samples = np.pad(samples, (self.n_fft // 2, self.n_fft // 2), mode="reflect")
        frames = np.lib.stride_tricks.sliding_window_view(samples, self.n_fft)[::self.hop_length][:-1]
        window = np.hanning(self.n_fft + 1)[:-1].astype(np.float32)
        features = np.empty((self.mel_filters.shape[0], len(frames)), dtype=np.float32)
        for start in range(0, len(frames), self.batch_frames):
            block = frames[start:start + self.batch_frames] * window
            spectrum = np.fft.rfft(block, axis=-1).astype(np.complex64)
            magnitude = np.abs(spectrum.T) ** 2
            features[:, start:start + len(block)] = self.mel_filters @ magnitude
        np.maximum(features, 1e-10, out=features)
        np.log10(features, out=features)
        np.maximum(features, features.max() - 8.0, out=features)
        features += 4.0
        features /= 4.0
        return features
