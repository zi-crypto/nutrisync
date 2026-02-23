/**
 * NutriSync Live Coach System
 * 
 * Built based on SOLID principles:
 * - Single Responsibility Pattern: Separated into CameraManager, PoseEstimationService, UIRenderer, and LiveCoachController.
 * - Dependency Inversion: The Controller depends on injected instances rather than concrete creations where possible.
 */

// --- Core Utilities ---
class MathUtils {
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
        this.state = 'UP';
        this.reps = 0;
        this.feedback = "Ready";
        this.lastAngle = 180;
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

        const angleKnee = MathUtils.calculateAngle(hip, knee, ankle);

        // Form & State logic
        // 1. Fully Upright (Extend state reset deeper to ensure they lock out)
        if (angleKnee > 155) {
            if (this.state === 'ASCENDING' || this.state === 'DOWN') {
                this.reps++;
                this.feedback = `${this.reps}`; // Emits Rep count
            } else if (this.state === 'DESCENDING' && this.lastAngle > 110) {
                this.feedback = "Squat deeper next time.";
            } else if (this.state === 'UP' && isNaN(Number(this.feedback))) {
                this.feedback = "Ready";
            }
            this.state = 'UP';
        }
        // 2. Mid descent/ascent
        else if (angleKnee <= 155 && angleKnee > 125) {
            if (this.state === 'UP') {
                this.state = 'DESCENDING';
            } else if (this.state === 'DOWN') {
                this.state = 'ASCENDING';
            }
        }
        // 3. Deep Squat (Hitting depth)
        // Adjust threshold from < 95 to <= 125. A solid parallel squat is often around 90-110,
        // but 120 accommodates partial/stiffer squats and varying camera angles.
        else if (angleKnee <= 125) {
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
            angle: Math.round(angleKnee)
        };
    }
}

class ExerciseEngine {
    constructor() {
        this.currentProfile = new SquatProfile(); // Defaults to Squat for Phase 3
        this.latestResult = null;
    }

    update(landmarks) {
        if (!landmarks || landmarks.length < 33) return null;
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
            minDetectionConfidence: 0.5,
            minTrackingConfidence: 0.5
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
                this.uiRenderer.drawOverlayText(`Knee Angle: ${engineStatus.angle}`, 20, 460, '18px', '#FFF');

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
