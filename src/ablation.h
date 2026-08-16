#ifndef ABLATION_H
#define ABLATION_H

// Compile-time ablation switches for the fx-cmix ablation study.
//
// Every mechanism has a HAS_<NAME> constant that defaults to 1. Building with
// -DABLATE_<NAME> flips it to 0 and removes that mechanism from the ensemble.
// With no ABLATE_* flags defined this header changes nothing and the binary is
// identical to an unmodified build -- that null test is the first thing the
// harness checks.
//
// The point of the study is to rank mechanisms so research attention goes to
// the ones that earn the bits. See doc/ablation/README.md.

// ---------------------------------------------------------------------------
// Coupling
// ---------------------------------------------------------------------------
// ByteMixer (the LSTM) has exactly one input: PPM's 256-way byte distribution.
// See Predictor::Perceive() piping byte_model_->BytePredict() into
// byte_mixer_->SetInput(), and ByteMixer's num_models_ == 1. Removing PPM
// therefore removes the LSTM's only source of information, so ABLATE_PPMD
// implies ABLATE_LSTM.
//
// To attribute the two separately, compare:
//   ABLATE_LSTM -> LSTM gone, PPM still feeding the mixer directly
//   ABLATE_PPMD -> both gone
// and read the difference as PPM's own contribution.
#if defined(ABLATE_PPMD) && !defined(ABLATE_LSTM)
#define ABLATE_LSTM
#endif

// ---------------------------------------------------------------------------
// Ensemble members (one Add*() call each in Predictor::Predictor)
// ---------------------------------------------------------------------------

#ifdef ABLATE_FXCM              // 439 of the 490 layer-0 inputs
#define HAS_FXCM 0
#else
#define HAS_FXCM 1
#endif

#ifdef ABLATE_PPMD              // mod_ppmd byte model, 1 input
#define HAS_PPMD 0
#else
#define HAS_PPMD 1
#endif

#ifdef ABLATE_LSTM              // ByteMixer + Lstm, 1 input
#define HAS_LSTM 0
#else
#define HAS_LSTM 1
#endif

#ifdef ABLATE_BRACKET           // Bracket byte model + 1 direct + 1 indirect
#define HAS_BRACKET 0
#else
#define HAS_BRACKET 1
#endif

#ifdef ABLATE_WORD              // 18 indirect-ns + 6 match + 1 indirect-run
#define HAS_WORD 0
#else
#define HAS_WORD 1
#endif

#ifdef ABLATE_MATCH             // 10 order-N match models
#define HAS_MATCH 0
#else
#define HAS_MATCH 1
#endif

#ifdef ABLATE_DOUBLE_INDIRECT   // 11 indirect-hash indirect-ns models
#define HAS_DOUBLE_INDIRECT 0
#else
#define HAS_DOUBLE_INDIRECT 1
#endif

// ---------------------------------------------------------------------------
// Mixing and calibration
// ---------------------------------------------------------------------------

// Shelwien's two-stage SSE on the final probability. Ablating it also skips
// the ~450 MB allocation and its eager init loop, so expect a memory and time
// drop alongside any size change.
#ifdef ABLATE_SSE
#define HAS_SSE 0
#else
#define HAS_SSE 1
#endif

// Point every layer-0 mixer gate at the constant context instead of its own.
// Deliberately keeps the mixer count and learning rates unchanged, so this
// measures context gating alone rather than confounding it with ensemble size.
#ifdef ABLATE_MIXER_GATING
#define HAS_MIXER_GATING 0
#else
#define HAS_MIXER_GATING 1
#endif

// Layer-0 mixers feed their outputs back to each other within a single bit
// (mixer i sees the outputs of mixers 0..i-1 as extra inputs).
#ifdef ABLATE_MIXER_RECURRENCE
#define HAS_MIXER_RECURRENCE 0
#else
#define HAS_MIXER_RECURRENCE 1
#endif

// Skip connections re-injecting the raw fxcm and LSTM predictions into layer 1.
#ifdef ABLATE_MIXER_SKIP
#define HAS_MIXER_SKIP 0
#else
#define HAS_MIXER_SKIP 1
#endif

// The 1M/5M/25M step learning-rate decay schedule. Both the 1M and 5M
// thresholds are crossed on a 930 KB input, so this is live on our corpus.
#ifdef ABLATE_MIXER_DECAY
#define HAS_MIXER_DECAY 0
#else
#define HAS_MIXER_DECAY 1
#endif

// The *= (1 - 3e-6) weight decay applied every 1024 steps.
#ifdef ABLATE_MIXER_WDECAY
#define HAS_MIXER_WDECAY 0
#else
#define HAS_MIXER_WDECAY 1
#endif

// The hard bypass: when the LSTM emits exactly 0 or 1, its output is returned
// directly and the entire mixer and SSE stack is discarded for that bit.
#ifdef ABLATE_LSTM_OVERRIDE
#define HAS_LSTM_OVERRIDE 0
#else
#define HAS_LSTM_OVERRIDE 1
#endif

// ---------------------------------------------------------------------------
// Preprocessing
// ---------------------------------------------------------------------------
// Note the three preprocessing levels below this one need no flag at all --
// the CLI already has them: "-c dict in out" (WRT + pretraining),
// "-c in out" (text detection only), "-n in out" (nothing).
//
// This flag keeps the dictionary transform but skips feeding the dictionary
// through the models first, which is the only way to tell the transform apart
// from the 412 KB of free training data it comes with.
#ifdef ABLATE_PRETRAIN
#define HAS_PRETRAIN 0
#else
#define HAS_PRETRAIN 1
#endif

// ---------------------------------------------------------------------------
// Derived sizes
// ---------------------------------------------------------------------------
// auxiliary_context_ averages the logistic of the fxcm and LSTM predictions.
// Guard against averaging nothing when both are ablated.
#define AUX_AVERAGED (HAS_FXCM + HAS_LSTM)

// How many extra stretched inputs layer 1 receives beyond the layer-0 outputs.
#if HAS_MIXER_SKIP
#define AUX_SKIP_INPUTS (HAS_FXCM + HAS_LSTM)
#else
#define AUX_SKIP_INPUTS 0
#endif

#endif
