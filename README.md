SatSim is a lightweight, web-based space mission analysis application designed to simulate satellite trajectories and compute ground station line-of-sight visibility. Inspired by Systems Tool Kit (STK), it acts as a self-contained astrodynamics dashboard built entirely on Python's core scientific and web engineering ecosystem.  Core Concept & CapabilityOrbital Mechanics Engine: Calculates satellite positions using classical Keplerian elements ($a, e, i, \Omega, \omega, \nu$) and propagates low Earth orbits (LEO) over time using a numerical Runge-Kutta solver (scipy==1.7.1) that factors in Earth's $\text{J}_2$ gravitational oblateness perturbation.  Coordinate Transformations: Handles precision transformations between Earth-Centered Inertial (ECI / GCRS) and Earth-Centered Earth-Fixed (ECEF / ITRS) frames using astropy==4.3.1.  Ground Station Access Analysis: Computes topocentric elevation angles and slant ranges to determine real-time contact windows and pass durations for target ground locations.  Web UI & Persistence: Features a dynamic web dashboard driven by Flask==1.1.2 with an underlying SQLAlchemy==1.4.22 ORM database to store satellite parameters, ground station profiles, and historical pass calculations.  Key Technical StackPython# SatSim Core Dependency Map
# Running strictly within local environment bounds:

import astropy     # Version 4.3.1  - Coordinate frames & UTC conversions
import scipy       # Version 1.7.1  - RK45 orbit integration (solve_ivp)
import numpy       # Version 1.20.3 - Vector mathematics & orbital elements
import pandas      # Version 1.3.4  - Pass schedule & time-series dataframes
import Flask       # Version 1.1.2  - REST API & Web Dashboard routing
import SQLAlchemy  # Version 1.4.22 - Persistent storage for scenarios & passes
import matplotlib  # Version 3.4.3  - Ground track & trajectory plotting
