"""SQLAlchemy ORM entities.

Persistence covers scenario *definitions* (satellites, ground stations,
timing) and simulation *outcomes* (runs, metrics, pass records).  Bulk
ephemeris samples are deliberately not stored -- they are cheap to
recompute and would dominate the database; plots derived from them are
written to the instance directory instead.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .core.constants import R_EARTH_EQ_KM
from .core.elements import ClassicalElements
from .core.stations import StationGeometry
from .db import Base


class Scenario(Base):
    """A self-contained analysis case: epoch + duration + assets."""

    __tablename__ = "scenarios"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, default="")
    start_time = Column(DateTime, nullable=False)  # naive UTC
    duration_s = Column(Float, nullable=False, default=86400.0)
    time_step_s = Column(Float, nullable=False, default=60.0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    satellites = relationship(
        "Satellite", back_populates="scenario",
        cascade="all, delete-orphan", order_by="Satellite.id",
    )
    ground_stations = relationship(
        "GroundStation", back_populates="scenario",
        cascade="all, delete-orphan", order_by="GroundStation.id",
    )
    runs = relationship(
        "SimulationRun", back_populates="scenario",
        cascade="all, delete-orphan", order_by="SimulationRun.id",
    )

    @property
    def end_time(self) -> datetime:
        return self.start_time + timedelta(seconds=self.duration_s)

    def to_dict(self, include_children: bool = False) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "start_time": self.start_time.isoformat(),
            "duration_s": self.duration_s,
            "time_step_s": self.time_step_s,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "num_satellites": len(self.satellites),
            "num_ground_stations": len(self.ground_stations),
            "num_runs": len(self.runs),
        }
        if include_children:
            data["satellites"] = [s.to_dict() for s in self.satellites]
            data["ground_stations"] = [g.to_dict() for g in self.ground_stations]
            data["runs"] = [r.to_dict() for r in self.runs]
        return data


class Satellite(Base):
    """A satellite defined by classical elements at the scenario epoch."""

    __tablename__ = "satellites"

    id = Column(Integer, primary_key=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    name = Column(String(120), nullable=False)
    constellation = Column(String(120), default="")  # grouping label, optional
    semi_major_axis_km = Column(Float, nullable=False)
    eccentricity = Column(Float, nullable=False, default=0.0)
    inclination_deg = Column(Float, nullable=False)
    raan_deg = Column(Float, nullable=False, default=0.0)
    arg_perigee_deg = Column(Float, nullable=False, default=0.0)
    true_anomaly_deg = Column(Float, nullable=False, default=0.0)

    scenario = relationship("Scenario", back_populates="satellites")

    def to_elements(self) -> ClassicalElements:
        return ClassicalElements(
            semi_major_axis_km=self.semi_major_axis_km,
            eccentricity=self.eccentricity,
            inclination_deg=self.inclination_deg,
            raan_deg=self.raan_deg,
            arg_perigee_deg=self.arg_perigee_deg,
            true_anomaly_deg=self.true_anomaly_deg,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scenario_id": self.scenario_id,
            "name": self.name,
            "constellation": self.constellation or "",
            "semi_major_axis_km": self.semi_major_axis_km,
            "eccentricity": self.eccentricity,
            "inclination_deg": self.inclination_deg,
            "raan_deg": self.raan_deg,
            "arg_perigee_deg": self.arg_perigee_deg,
            "true_anomaly_deg": self.true_anomaly_deg,
            "perigee_altitude_km": round(
                self.semi_major_axis_km * (1 - self.eccentricity)
                - R_EARTH_EQ_KM, 3
            ),
        }


class GroundStation(Base):
    __tablename__ = "ground_stations"

    id = Column(Integer, primary_key=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    name = Column(String(120), nullable=False)
    latitude_deg = Column(Float, nullable=False)
    longitude_deg = Column(Float, nullable=False)
    altitude_m = Column(Float, nullable=False, default=0.0)
    min_elevation_deg = Column(Float, nullable=False, default=5.0)

    scenario = relationship("Scenario", back_populates="ground_stations")

    def to_geometry(self) -> StationGeometry:
        return StationGeometry(
            name=self.name,
            latitude_deg=self.latitude_deg,
            longitude_deg=self.longitude_deg,
            altitude_m=self.altitude_m,
            min_elevation_deg=self.min_elevation_deg,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scenario_id": self.scenario_id,
            "name": self.name,
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
            "altitude_m": self.altitude_m,
            "min_elevation_deg": self.min_elevation_deg,
        }


class SimulationRun(Base):
    """One execution of a scenario, with its viability metrics."""

    __tablename__ = "simulation_runs"

    id = Column(Integer, primary_key=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    status = Column(String(32), nullable=False, default="completed")
    elapsed_s = Column(Float)  # wall-clock compute time
    metrics_json = Column(Text, default="{}")
    plots_json = Column(Text, default="[]")  # plot file names in instance dir

    scenario = relationship("Scenario", back_populates="runs")
    passes = relationship(
        "PassRecord", back_populates="run",
        cascade="all, delete-orphan", order_by="PassRecord.start_time",
    )

    @property
    def metrics(self) -> dict:
        try:
            return json.loads(self.metrics_json or "{}")
        except ValueError:
            return {}

    @property
    def plot_files(self) -> list:
        try:
            return json.loads(self.plots_json or "[]")
        except ValueError:
            return []

    def to_dict(self, include_passes: bool = False) -> dict:
        data = {
            "id": self.id,
            "scenario_id": self.scenario_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "status": self.status,
            "elapsed_s": self.elapsed_s,
            "metrics": self.metrics,
            "plots": self.plot_files,
            "num_passes": len(self.passes),
        }
        if include_passes:
            data["passes"] = [p.to_dict() for p in self.passes]
        return data


class PassRecord(Base):
    """A stored contact window between one satellite and one station."""

    __tablename__ = "passes"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("simulation_runs.id"), nullable=False)
    satellite_name = Column(String(120), nullable=False)
    station_name = Column(String(120), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    duration_s = Column(Float, nullable=False)
    max_elevation_deg = Column(Float, nullable=False)

    run = relationship("SimulationRun", back_populates="passes")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "satellite": self.satellite_name,
            "station": self.station_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_s": self.duration_s,
            "max_elevation_deg": self.max_elevation_deg,
        }
