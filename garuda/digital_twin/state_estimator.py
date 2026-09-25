"""
Uncertainty Quantification & Kalman State Estimator
Combines first-principles physics model predictions with noisy sensor observations
to produce optimal state estimates with quantified uncertainty bounds (confidence intervals).
"""

import math
from typing import Dict, Any, Optional, Tuple


class ScalarKalmanFilter:
    """
    1D Discrete Kalman Filter for uncertainty quantification on state estimates.
    Tracks state mean (x) and variance/covariance (P).
    """

    def __init__(
        self,
        initial_value: float = 0.0,
        initial_variance: float = 1.0,
        process_noise_q: float = 0.01,
        measurement_noise_r: float = 0.10
    ):
        self.x = float(initial_value)          # State estimate
        self.P = float(initial_variance)       # Estimate variance (uncertainty)
        self.Q = float(process_noise_q)        # Process noise variance
        self.R = float(measurement_noise_r)    # Sensor measurement noise variance

    def predict(self, dt: float = 0.1, model_prediction: Optional[float] = None) -> None:
        """
        Prediction Step:
        Physics model updates the state estimate. Uncertainty (P) grows over time (Q * dt).
        """
        if model_prediction is not None:
            self.x = float(model_prediction)
        self.P += self.Q * max(0.001, dt)

    def update(self, measurement: float) -> float:
        """
        Correction / Measurement Step:
        Fuses sensor observation with prior prediction via Kalman Gain (K).
        Returns the innovation residual (measurement - x).
        """
        # Kalman Gain: K = P / (P + R)
        K = self.P / (self.P + self.R)
        residual = float(measurement) - self.x

        self.x += K * residual
        self.P = max(1e-6, (1.0 - K) * self.P)
        return residual

    @property
    def standard_deviation(self) -> float:
        """1-sigma standard deviation (uncertainty in native units)."""
        return math.sqrt(max(0.0, self.P))

    def confidence_bounds(self, num_sigmas: float = 2.0) -> Tuple[float, float]:
        """
        Returns (lower_bound, upper_bound) for confidence interval.
        num_sigmas=1.0 -> ~68% confidence
        num_sigmas=2.0 -> ~95% confidence
        """
        margin = num_sigmas * self.standard_deviation
        return self.x - margin, self.x + margin


class DigitalTwinStateEstimator:
    """
    Multivariate estimator tracking position, velocity, battery health, and endurance.
    Maintains uncertainty matrices and outputs confidence bounds for the digital twin dashboard.
    """

    def __init__(self):
        # 3D Position Filters (meters)
        self.kf_north = ScalarKalmanFilter(0.0, 1.0, process_noise_q=0.05, measurement_noise_r=0.25)
        self.kf_east = ScalarKalmanFilter(0.0, 1.0, process_noise_q=0.05, measurement_noise_r=0.25)
        self.kf_alt = ScalarKalmanFilter(0.0, 0.5, process_noise_q=0.02, measurement_noise_r=0.10)

        # Dynamic State Filters
        self.kf_airspeed = ScalarKalmanFilter(0.0, 0.5, process_noise_q=0.08, measurement_noise_r=0.30)
        self.kf_wind = ScalarKalmanFilter(0.0, 0.5, process_noise_q=0.10, measurement_noise_r=0.40)

        # Vehicle Health & Endurance Filters
        self.kf_soc = ScalarKalmanFilter(100.0, 1.0, process_noise_q=0.005, measurement_noise_r=0.50)
        self.kf_endurance_s = ScalarKalmanFilter(900.0, 100.0, process_noise_q=1.0, measurement_noise_r=25.0)

    def predict_physics(
        self,
        predicted_alt_m: float,
        predicted_airspeed_ms: float,
        predicted_wind_ms: float,
        predicted_soc: float,
        predicted_endurance_s: float,
        dt: float = 0.1
    ) -> None:
        """
        Advances all filters using theoretical physics model predictions.
        """
        self.kf_alt.predict(dt, predicted_alt_m)
        self.kf_airspeed.predict(dt, predicted_airspeed_ms)
        self.kf_wind.predict(dt, predicted_wind_ms)
        self.kf_soc.predict(dt, predicted_soc)
        self.kf_endurance_s.predict(dt, predicted_endurance_s)

    def update_sensor_telemetry(
        self,
        measured_alt_m: Optional[float] = None,
        measured_airspeed_ms: Optional[float] = None,
        measured_wind_ms: Optional[float] = None,
        measured_soc: Optional[float] = None
    ) -> None:
        """
        Fuses noisy telemetry observations from GPS / Barometer / Battery monitor.
        """
        if measured_alt_m is not None:
            self.kf_alt.update(measured_alt_m)
        if measured_airspeed_ms is not None:
            self.kf_airspeed.update(measured_airspeed_ms)
        if measured_wind_ms is not None:
            self.kf_wind.update(measured_wind_ms)
        if measured_soc is not None:
            self.kf_soc.update(measured_soc)

    def snapshot(self) -> Dict[str, Any]:
        """
        Outputs state estimates along with 95% confidence bounds (± 2 sigma)
        for telemetry logs and the dashboard visualization.
        """
        alt_low, alt_high = self.kf_alt.confidence_bounds(2.0)
        endur_low, endur_high = self.kf_endurance_s.confidence_bounds(2.0)
        soc_low, soc_high = self.kf_soc.confidence_bounds(2.0)

        return {
            "altitude": {
                "estimate_m": round(self.kf_alt.x, 2),
                "uncertainty_m": round(self.kf_alt.standard_deviation, 2),
                "ci_95": [round(alt_low, 2), round(alt_high, 2)]
            },
            "airspeed": {
                "estimate_ms": round(self.kf_airspeed.x, 2),
                "uncertainty_ms": round(self.kf_airspeed.standard_deviation, 2)
            },
            "wind_speed": {
                "estimate_ms": round(self.kf_wind.x, 2),
                "uncertainty_ms": round(self.kf_wind.standard_deviation, 2)
            },
            "battery_soc": {
                "estimate_percent": round(self.kf_soc.x, 1),
                "uncertainty_percent": round(self.kf_soc.standard_deviation, 1),
                "ci_95": [round(soc_low, 1), round(soc_high, 1)]
            },
            "endurance": {
                "estimate_s": round(self.kf_endurance_s.x, 1),
                "estimate_min": round(self.kf_endurance_s.x / 60.0, 1),
                "uncertainty_min": round(self.kf_endurance_s.standard_deviation / 60.0, 1),
                "ci_95_min": [round(endur_low / 60.0, 1), round(endur_high / 60.0, 1)]
            }
        }
