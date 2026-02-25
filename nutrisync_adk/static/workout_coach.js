/**
 * NutriSync Live Coach System
 * 
 * Built based on SOLID principles:
 * - Single Responsibility Pattern: Separated into CameraManager, PoseEstimationService, UIRenderer, and LiveCoachController.
 * - Dependency Inversion: The Controller depends on injected instances rather than concrete creations where possible.
 */

// --- Core Utilities ---
class MathUtils {
    static EMA_ALPHA = 0.4;

    /**
     * Calculates the angle ABC around vertex B.
     * @param {Object} a {x, y}
     * @param {Object} b {x, y}
     * @param {Object} c {x, y}
     * @returns {number} Angle in degrees [0, 180]
     */
    static calculateAngle(a, b, c) {
        if (!a || !b || !c) return 0;
        let radians = Math.atan2(c.y - b.y, c.x - b.x) - Math.atan2(a.y - b.y, a.x - b.x);
        let angle = Math.abs(radians * 180.0 / Math.PI);
        if (angle > 180.0) angle = 360 - angle;
        return angle;
    }

    /**
     * Exponential Moving Average to smooth out camera jitter.
     */
    static calculateEMA(current, previous) {
        if (previous === null || previous === undefined || isNaN(previous)) return current;
        return (current * this.EMA_ALPHA) + (previous * (1 - this.EMA_ALPHA));
    }
}

class VoiceCoach {
    constructor() {
        this.synth = window.speechSynthesis;
        this.lastSpokenText = "";
        this.lastFeedbackText = ""; // Track distinct feedback separate from reps
        this.lastFeedbackTime = 0;
        this.debounceMs = 3000; // prevent spam
    }

    speak(text, isRepCount = false) {
        if (!this.synth || !text) return;

        const now = Date.now();

        // If it's general feedback, bounce if it's the exact same phrase spoken recently
        if (!isRepCount && text === this.lastFeedbackText && (now - this.lastFeedbackTime) < this.debounceMs) {
            return;
        }

        // We don't want to cancel the speech if it's currently speaking a Rep count (e.g., "One").
        // But if it's currently speaking long feedback, it's ok to interrupt it with a Rep.
        if (this.synth.speaking && !isRepCount) {
            return; // Don't interrupt current speech with more generic feedback
        } else if (this.synth.speaking && isRepCount) {
            this.synth.cancel(); // Interrupt long feedback with the critical Rep count
        }

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.1; // Slightly faster to avoid cutting off
        this.synth.speak(utterance);

        if (!isRepCount) {
            this.lastFeedbackText = text;
            this.lastFeedbackTime = now;
        }

        this.lastSpokenText = text;
    }

    stop() {
        if (this.synth) this.synth.cancel();
    }
}

// --- Exercise Logic Profiles ---
class SquatProfile {
    constructor() {
        this.reset();
    }

    reset() {
        this.state = 'UP';
        this.reps = 0;
        this.feedback = "Ready";
        this.lastAngle = 180;
        this.smoothedAngle = undefined;
    }

    processConstraints(landmarks) {
        // MediaPipe indices: Hip(23/24), Knee(25/26), Ankle(27/28)
        const leftHip = landmarks[23], leftKnee = landmarks[25], leftAnkle = landmarks[27];
        const rightHip = landmarks[24], rightKnee = landmarks[26], rightAnkle = landmarks[28];

        // Use the side with better average visibility
        const leftVis = leftHip.visibility + leftKnee.visibility + leftAnkle.visibility;
        const rightVis = rightHip.visibility + rightKnee.visibility + rightAnkle.visibility;
        const useLeft = leftVis >= rightVis;

        const hip = useLeft ? leftHip : rightHip;
        const knee = useLeft ? leftKnee : rightKnee;
        const ankle = useLeft ? leftAnkle : rightAnkle;

        const rawAngleKnee = MathUtils.calculateAngle(hip, knee, ankle);
        this.smoothedAngle = MathUtils.calculateEMA(rawAngleKnee, this.smoothedAngle);
        const angleKnee = this.smoothedAngle;

        // Exercise Cross-Contamination Filter: Prevent Pushups in Squat Mode
        // 1. In a pushup, the body is stretched out horizontally on the floor.
        //    Therefore, the horizontal distance (X-axis) between shoulders and ankles is large.
        // 2. In a squat, the head is vertically aligned over the feet, so X-distance is small.
        // We calculate horizontal distance as a percentage of the screen width (0 to 1).
        const leftShoulder = landmarks[11], rightShoulder = landmarks[12];
        const shoulder = useLeft ? leftShoulder : rightShoulder;
        const horizontalDistance = Math.abs(shoulder.x - ankle.x);

        // If body is stretched across screen (> 35% of width)
        if (horizontalDistance > 0.35) {
            return {
                state: this.state, // Preserve state so it doesn't reset
                reps: this.reps,
                feedback: "Stand up to squat!",
                angle: Math.round(angleKnee),
                instruction: "Camera placement: Waist height, direct side view."
            };
        }

        // Form & State logic
        // 1. Fully Upright (Extend state reset deeper to ensure they lock out)
        if (angleKnee > 160) {
            if (this.state === 'ASCENDING') {
                this.reps++;
                this.feedback = `${this.reps}`; // Emits Rep count only on completion
            } else if (this.state === 'DESCENDING') {
                this.feedback = "Squat deeper next time.";
            } else if (this.state === 'UP' && isNaN(Number(this.feedback))) {
                this.feedback = "Ready";
            }
            this.state = 'UP';
        }
        // 2. Mid descent/ascent
        else if (angleKnee <= 160 && hip.y < knee.y) {
            if (this.state === 'UP') {
                this.state = 'DESCENDING';
                this.feedback = "Ready"; // Clear previous rep count
            } else if (this.state === 'DOWN') {
                this.state = 'ASCENDING';
            }
        }
        // 3. Deep Squat (Hitting depth - Thigh Parallel Heuristic)
        // Ignoring static angle bounds at the bottom and replacing it with the biomechanical truth: target hip crease below top of knee.
        else if (hip.y >= knee.y) {
            if (this.state === 'DESCENDING') {
                this.state = 'DOWN';
                this.feedback = "Good depth, push up!";
            }
        }

        this.lastAngle = angleKnee;

        return {
            state: this.state,
            reps: this.reps,
            feedback: this.feedback,
            angle: Math.round(angleKnee),
            instruction: "Camera placement: Waist height, direct side view."
        };
    }
}

class PushupProfile {
    constructor() {
        this.reset();
    }

    reset() {
        this.state = 'SETUP';
        this.reps = 0;
        this.feedback = "Ready";
        this.lastAngle = 180;
        this.smoothedAngle = undefined;

        // Calibration
        this.setupStartTime = 0;
        this.distances = [];
        this.maxRange = 0;
    }

    processConstraints(landmarks) {
        // MediaPipe indices: Shoulder(11/12), Elbow(13/14), Wrist(15/16), Hip(23/24), Ankle(27/28)
        const leftShoulder = landmarks[11], leftElbow = landmarks[13], leftWrist = landmarks[15];
        const rightShoulder = landmarks[12], rightElbow = landmarks[14], rightWrist = landmarks[16];
        const leftHip = landmarks[23], leftAnkle = landmarks[27];
        const rightHip = landmarks[24], rightAnkle = landmarks[28];

        // Use the side with better average visibility for arms
        const leftVis = leftShoulder.visibility + leftElbow.visibility + leftWrist.visibility;
        const rightVis = rightShoulder.visibility + rightElbow.visibility + rightWrist.visibility;
        const useLeft = leftVis >= rightVis;

        const shoulder = useLeft ? leftShoulder : rightShoulder;
        const elbow = useLeft ? leftElbow : rightElbow;
        const wrist = useLeft ? leftWrist : rightWrist;
        const hip = useLeft ? leftHip : rightHip;
        const ankle = useLeft ? leftAnkle : rightAnkle;

        const rawAngleElbow = MathUtils.calculateAngle(shoulder, elbow, wrist);
        this.smoothedAngle = MathUtils.calculateEMA(rawAngleElbow, this.smoothedAngle);
        const angleElbow = this.smoothedAngle;

        const angleBack = MathUtils.calculateAngle(shoulder, hip, ankle);

        // Dynamic Range Calibration
        const currentDistance = Math.hypot(shoulder.x - wrist.x, shoulder.y - wrist.y);

        if (this.state === 'SETUP') {
            if (angleElbow > 150) {
                if (this.setupStartTime === 0) {
                    this.setupStartTime = Date.now();
                    this.feedback = "Hold plank to calibrate...";
                } else if (Date.now() - this.setupStartTime > 3000) {
                    this.maxRange = this.distances.reduce((a, b) => a + b, 0) / this.distances.length;
                    this.state = 'UP';
                    this.feedback = "Calibrated! Ready.";
                } else {
                    this.distances.push(currentDistance);
                    this.feedback = "Hold plank to calibrate...";
                }
            } else {
                this.setupStartTime = 0;
                this.distances = [];
                this.feedback = "Straighten arms to calibrate";
            }

            return {
                state: this.state,
                reps: this.reps,
                feedback: this.feedback,
                angle: Math.round(angleElbow),
                label: 'Setup',
                instruction: "Keep arms perfectly straight in plank for 3 seconds."
            };
        }

        // Exercise Cross-Contamination Filter: Prevent Squats in Pushup Mode
        // 1. In a pushup, the body is horizontal. 
        // 2. In a squat, the body is vertical (Shoulder Y is massively above Ankle Y).
        // 3. We check the vertical distance (Y-axis) between Shoulder and Ankle.
        const verticalDistance = Math.abs(ankle.y - shoulder.y);

        // If the vertical distance is massive (> 50% of the screen height), 
        // the user is standing, not in a pushup position.
        if (verticalDistance > 0.5) {
            return {
                state: this.state, // Preserve state
                reps: this.reps,
                feedback: "Get into a plank!",
                angle: Math.round(angleElbow),
                label: 'Elbow Angle',
                instruction: "Camera placement: Floor level, 45-degree angle side view."
            };
        }

        // Strict Form check: Back should be relatively straight (approx 180). 
        // If it dips significantly below 130 (more forgiving for camera angles), trigger a form warning.
        if (angleBack < 130 && this.state !== 'DOWN') {
            this.feedback = "Keep back straight!";
            // We can optionally return early or just let the feedback sit. Let's let it sit.
        }

        // Form & State logic (Dynamic Distance + Smoothed Angle)
        if (angleElbow > 160) {
            if (this.state === 'ASCENDING') {
                this.reps++;
                this.feedback = `${this.reps}`; // Emits Rep count only on completion
            } else if (this.state === 'DESCENDING') {
                this.feedback = "Go lower!";
            } else if (this.state === 'UP' && isNaN(Number(this.feedback)) && this.feedback !== "Calibrated! Ready.") {
                this.feedback = "Ready";
            }
            this.state = 'UP';
        }
        else if (angleElbow <= 160 && currentDistance > this.maxRange * 0.45) {
            if (this.state === 'UP') {
                this.state = 'DESCENDING';
                this.feedback = "Ready"; // Clear previous rep count
            } else if (this.state === 'DOWN') {
                this.state = 'ASCENDING';
            }
        }
        else if (currentDistance <= this.maxRange * 0.45) {
            // DOWN state dynamically determined by actual pixel distance shrinking
            if (this.state === 'DESCENDING') {
                this.state = 'DOWN';
                this.feedback = "Good depth, push up!";
            }
        }

        this.lastAngle = angleElbow;

        return {
            state: this.state,
            reps: this.reps,
            feedback: this.feedback,
            angle: Math.round(angleElbow),
            label: 'Elbow Angle',
            instruction: "Camera placement: Floor level, 45-degree angle side view."
        };
    }
}

class PullProfile {
    constructor() {
        this.reset();
    }

    reset() {
        this.state = 'SETUP'; // Requires calibration first
        this.reps = 0;
        this.feedback = "Ready";
        this.lastAngle = 180;
        this.smoothedAngle = undefined;

        // Calibration
        this.setupStartTime = 0;
        this.distances = [];
        this.maxRange = 0;
    }

    processConstraints(landmarks) {
        // MediaPipe indices: Nose(0), Shoulder(11/12), Elbow(13/14), Wrist(15/16), Hip(23/24)
        const leftShoulder = landmarks[11], leftElbow = landmarks[13], leftWrist = landmarks[15], leftHip = landmarks[23];
        const rightShoulder = landmarks[12], rightElbow = landmarks[14], rightWrist = landmarks[16], rightHip = landmarks[24];

        const leftVis = leftShoulder.visibility + leftElbow.visibility + leftWrist.visibility;
        const rightVis = rightShoulder.visibility + rightElbow.visibility + rightWrist.visibility;
        const useLeft = leftVis >= rightVis;

        const shoulder = useLeft ? leftShoulder : rightShoulder;
        const elbow = useLeft ? leftElbow : rightElbow;
        const wrist = useLeft ? leftWrist : rightWrist;
        const hip = useLeft ? leftHip : rightHip;

        const rawAngleElbow = MathUtils.calculateAngle(shoulder, elbow, wrist);
        this.smoothedAngle = MathUtils.calculateEMA(rawAngleElbow, this.smoothedAngle);
        const angleElbow = this.smoothedAngle;

        // Dynamic Range Calibration
        const currentDistance = Math.abs(shoulder.y - wrist.y);

        if (this.state === 'SETUP') {
            if (angleElbow > 150 && wrist.y < shoulder.y) {
                if (this.setupStartTime === 0) {
                    this.setupStartTime = Date.now();
                    this.feedback = "Hang straight to calibrate...";
                } else if (Date.now() - this.setupStartTime > 3000) {
                    this.maxRange = this.distances.reduce((a, b) => a + b, 0) / this.distances.length;
                    this.state = 'UP';
                    this.feedback = "Calibrated! Ready.";
                } else {
                    this.distances.push(currentDistance);
                    this.feedback = "Hang straight to calibrate...";
                }
            } else {
                this.setupStartTime = 0;
                this.distances = [];
                this.feedback = "Fully extend arms over head to calibrate";
            }
            return {
                state: this.state,
                reps: this.reps,
                feedback: this.feedback,
                angle: Math.round(angleElbow),
                label: 'Setup',
                instruction: "Keep arms perfectly straight over head for 3 seconds."
            };
        }

        // Exercise Cross-Contamination Filter: Prevent Squat/Pushup counting as Pull-up
        // In a pulling motion, the hands (wrists) must start and generally remain above the shoulders.
        // MediaPipe Y: 0 is top of screen, 1 is bottom. So wrist Y should be smaller than shoulder Y.
        // We add a strict check that if wrists drop massively below shoulders, ignore.
        if (wrist.y > shoulder.y + 0.1) {
            return {
                state: this.state,
                reps: this.reps,
                feedback: "Reach hands UP for pullups!",
                angle: Math.round(angleElbow),
                label: 'Elbow Angle',
                instruction: "Camera placement: Camera higher up, capturing full arm extension."
            };
        }

        // Form & State logic (Dynamic Distance + Smoothed Angle)
        if (angleElbow > 150) {
            if (this.state === 'ASCENDING') {
                this.reps++;
                this.feedback = `${this.reps}`; // Emits Rep count only on completion
            } else if (this.state === 'DESCENDING') {
                this.feedback = "Pull higher!";
            } else if (this.state === 'UP' && isNaN(Number(this.feedback)) && this.feedback !== "Calibrated! Ready.") {
                this.feedback = "Ready";
            }
            this.state = 'UP'; // Arms extended
        }
        else if (angleElbow <= 150 && currentDistance > this.maxRange * 0.25) {
            if (this.state === 'UP') {
                this.state = 'DESCENDING'; // Starting the pull
                this.feedback = "Ready"; // Clear previous rep count
            } else if (this.state === 'DOWN') {
                this.state = 'ASCENDING'; // Releasing the pull
            }
        }
        else if (currentDistance <= this.maxRange * 0.25) {
            if (this.state === 'DESCENDING') {
                this.state = 'DOWN'; // Contracted position
                this.feedback = "Good pull";
            }
        }

        this.lastAngle = angleElbow;

        return {
            state: this.state,
            reps: this.reps,
            feedback: this.feedback,
            angle: Math.round(angleElbow),
            label: 'Elbow Angle',
            instruction: "Camera placement: Camera higher up, capturing full arm extension."
        };
    }
}

class ExerciseEngine {
    constructor() {
        this.profiles = {
            'squat': new SquatProfile(),
            'pushup': new PushupProfile(),
            'pullup': new PullProfile()
        };
        this.currentProfile = this.profiles['squat']; // Default
        this.latestResult = null;
    }

    setExercise(exerciseName) {
        if (this.profiles[exerciseName]) {
            this.currentProfile = this.profiles[exerciseName];
            // Reset state using profile-specific logic (so SETUP isn't bypassed)
            this.currentProfile.reset();
            this.latestResult = null;
            return true;
        }
        return false;
    }

    update(landmarks) {
        if (!landmarks || landmarks.length < 33) return null;

        // --- False Positive Filter ---
        // MediaPipe tries to find humans in random objects (like tripods) if the threshold is low.
        // We ensure that key anchor points (like the face or shoulders) are actually visible 
        // with high confidence before we consider this a valid skeleton.
        const noseVis = landmarks[0]?.visibility || 0;
        const leftShoulderVis = landmarks[11]?.visibility || 0;
        const rightShoulderVis = landmarks[12]?.visibility || 0;

        // If neither the nose nor both shoulders are reasonably visible, we assume it's a false positive object
        if (noseVis < 0.65 && (leftShoulderVis < 0.65 || rightShoulderVis < 0.65)) {
            return {
                state: this.currentProfile.state,
                reps: this.currentProfile.reps,
                feedback: "Ensure upper body is clearly visible.",
                angle: 0,
                instruction: this.currentProfile.instruction || ""
            };
        }

        this.latestResult = this.currentProfile.processConstraints(landmarks);
        return this.latestResult;
    }
}

// 1. Single Responsibility: Manage Camera Feed
class CameraManager {
    constructor(videoElement, width = 640, height = 480) {
        this.videoElement = videoElement;
        this.width = width;
        this.height = height;
        this.camera = null;
        this.stream = null;
    }

    async start(onFrameCallback) {
        if (!window.Camera) {
            console.error("MediaPipe Camera Utils not loaded.");
            return;
        }

        try {
            // 1. Explicitly request camera permissions
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: this.width,
                    height: this.height,
                    facingMode: "user"
                }
            });

            // 2. Assign stream to video element
            this.videoElement.srcObject = this.stream;

            // 3. Force video to play (required by some browsers before MediaPipe can read it)
            await this.videoElement.play();

            // 4. Initialize MediaPipe Camera *after* we know the video is playing
            this.camera = new window.Camera(this.videoElement, {
                onFrame: async () => {
                    await onFrameCallback(this.videoElement);
                },
                width: this.width,
                height: this.height
            });

            this.camera.start();
            console.log("CameraManager started with explicit stream.");
        } catch (err) {
            console.error("Error accessing camera: ", err);
            alert("Unable to access camera: " + err.message);
        }
    }

    stop() {
        if (this.camera) {
            this.camera.stop();
        }
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.videoElement.srcObject = null;
        }
    }
}

// 2. Single Responsibility: Manage Pose Estimation
class PoseEstimationService {
    constructor() {
        if (!window.Pose) {
            console.error("MediaPipe Pose not loaded.");
            return;
        }

        this.pose = new window.Pose({
            locateFile: (file) => {
                return `https://cdn.jsdelivr.net/npm/@mediapipe/pose/${file}`;
            }
        });

        this.pose.setOptions({
            modelComplexity: 1, // 0 = fast/low accu, 1 = balanced, 2 = slow/high accu
            smoothLandmarks: true,
            enableSegmentation: false,
            smoothSegmentation: false,
            minDetectionConfidence: 0.7,
            minTrackingConfidence: 0.7
        });
    }

    setResultHandler(callback) {
        this.pose.onResults(callback);
    }

    async processFrame(imageElement) {
        await this.pose.send({ image: imageElement });
    }
}

// 3. Single Responsibility: Render UI/Landmarks to Canvas
class UIRenderer {
    constructor(canvasElement) {
        this.canvasElement = canvasElement;
        this.ctx = canvasElement.getContext('2d');
    }

    clear() {
        this.ctx.clearRect(0, 0, this.canvasElement.width, this.canvasElement.height);
    }

    drawImage(image) {
        this.ctx.drawImage(image, 0, 0, this.canvasElement.width, this.canvasElement.height);
    }

    drawLandmarks(results) {
        if (!results.poseLandmarks) return;

        if (window.drawConnectors && window.drawLandmarks && window.POSE_CONNECTIONS) {
            window.drawConnectors(this.ctx, results.poseLandmarks, window.POSE_CONNECTIONS,
                { color: '#00FF00', lineWidth: 4 });
            window.drawLandmarks(this.ctx, results.poseLandmarks,
                { color: '#FF0000', lineWidth: 2 });
        }
    }

    drawOverlayText(text, x, y, size = '20px', color = 'white') {
        this.ctx.font = `${size} Arial`;
        this.ctx.fillStyle = color;
        this.ctx.fillText(text, x, y);
    }

    render(results) {
        this.ctx.save();
        this.clear();

        // Draw the video frame
        this.drawImage(results.image);

        // Draw pose landmarks
        this.drawLandmarks(results);

        this.ctx.restore();
    }
}

// 4. Orchestrator: Integrates modules (Dependency Injection pattern)
class LiveCoachController {
    constructor(cameraManager, poseService, uiRenderer, exerciseEngine) {
        this.cameraManager = cameraManager;
        this.poseService = poseService;
        this.uiRenderer = uiRenderer;
        this.exerciseEngine = exerciseEngine;
        this.voiceCoach = new window.VoiceCoach();

        this.isRunning = false;
        this.lastFeedback = "";

        // Bind the results handler
        this.poseService.setResultHandler(this.onPoseResults.bind(this));
    }

    start() {
        if (this.isRunning) return;
        this.isRunning = true;

        // Pass the frame processing callback to the camera manager
        this.cameraManager.start(async (videoFrame) => {
            await this.poseService.processFrame(videoFrame);
        });
    }

    stop() {
        this.isRunning = false;
        this.cameraManager.stop();
        this.uiRenderer.clear();
    }

    onPoseResults(results) {
        if (!this.isRunning) return;

        // Render base video + skeletal frame
        this.uiRenderer.render(results);

        if (results.poseLandmarks) {
            // Process form & reps
            const engineStatus = this.exerciseEngine.update(results.poseLandmarks);

            if (engineStatus) {
                // Render HUD
                this.uiRenderer.drawOverlayText(`Reps: ${engineStatus.reps}`, 20, 40, '30px', '#00FF00');
                this.uiRenderer.drawOverlayText(`Stage: ${engineStatus.state}`, 20, 80, '24px', '#FFF');
                this.uiRenderer.drawOverlayText(`Feedback: ${engineStatus.feedback}`, 20, 120, '20px', '#FFF');

                if (engineStatus.instruction) {
                    // Render camera instruction centered at the bottom
                    const instructionY = this.uiRenderer.canvasElement.height - 20;
                    this.uiRenderer.ctx.font = '16px Arial';
                    const textWidth = this.uiRenderer.ctx.measureText(engineStatus.instruction).width;
                    const textX = (this.uiRenderer.canvasElement.width - textWidth) / 2;

                    // Draw background box for readability
                    this.uiRenderer.ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
                    this.uiRenderer.ctx.fillRect(textX - 10, instructionY - 20, textWidth + 20, 26);
                    this.uiRenderer.drawOverlayText(engineStatus.instruction, textX, instructionY, '16px', '#FFD700');
                }

                const angleLabel = engineStatus.label || 'Knee Angle';
                this.uiRenderer.drawOverlayText(`${angleLabel}: ${engineStatus.angle}`, 20, 420, '18px', '#FFF');

                // Trigger voice coaching
                if (engineStatus.feedback !== "Ready" && engineStatus.feedback !== this.lastFeedback) {

                    // Check if the feedback is purely a number (a rep count)
                    const isRepCount = !isNaN(Number(engineStatus.feedback));

                    this.voiceCoach.speak(engineStatus.feedback, isRepCount);
                    this.lastFeedback = engineStatus.feedback;
                }
            }
        } else {
            this.uiRenderer.drawOverlayText("No Pose Detected", 20, 40, '24px', '#FF0000');
        }
    }
}

// Expose to window for UI binding
window.LiveCoachController = LiveCoachController;
window.CameraManager = CameraManager;
window.PoseEstimationService = PoseEstimationService;
window.UIRenderer = UIRenderer;
window.ExerciseEngine = ExerciseEngine;
window.VoiceCoach = VoiceCoach;
window.MathUtils = MathUtils;
