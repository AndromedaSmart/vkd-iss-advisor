from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from sgp4.api import Satrec, jday
from sgp4.conveniences import sat_epoch_datetime

from app.timeutil import as_utc, iter_steps

EARTH_KM = 6378.137
F_EARTH = 1.0 / 298.257223563


def load_satrec(line1, line2):
    sat = Satrec.twoline2rv(line1, line2)
    if sat.error:
        raise RuntimeError("SGP4 не принял TLE, код {0}".format(sat.error))
    return sat


def sat_epoch(sat):
    dt = sat_epoch_datetime(sat)
    return as_utc(dt)


def propagate(sat, dt):
    dt = as_utc(dt)
    jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second + dt.microsecond * 1e-6)
    err, r, v = sat.sgp4(jd, fr)
    if err:
        raise RuntimeError("SGP4 error {0} at {1}".format(err, dt.isoformat()))
    return r, v


def gmst_rad(dt):
    dt = as_utc(dt)
    jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second + dt.microsecond * 1e-6)
    jd_ut1 = jd + fr
    t = (jd_ut1 - 2451545.0) / 36525.0
    gmst_sec = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * t
        + 0.093104 * t * t
        - 6.2e-6 * t * t * t
    )
    return math.radians((gmst_sec % 86400.0) / 240.0)


def teme_to_geodetic(r, dt):
    theta = gmst_rad(dt)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    x = r[0] * cos_t + r[1] * sin_t
    y = -r[0] * sin_t + r[1] * cos_t
    z = r[2]
    lon = math.degrees(math.atan2(y, x))
    if lon > 180:
        lon -= 360
    if lon < -180:
        lon += 360
    r_xy = math.hypot(x, y)
    lat = math.atan2(z, r_xy)
    for _ in range(6):
        sin_lat = math.sin(lat)
        n = EARTH_KM / math.sqrt(1.0 - F_EARTH * (2.0 - F_EARTH) * sin_lat * sin_lat)
        lat = math.atan2(z + n * F_EARTH * (2.0 - F_EARTH) * sin_lat, r_xy)
    alt = r_xy / math.cos(lat) - EARTH_KM / math.sqrt(
        1.0 - F_EARTH * (2.0 - F_EARTH) * math.sin(lat) ** 2
    )
    return lat * 180.0 / math.pi, lon, alt


def sun_unit_approx(dt):
    dt = as_utc(dt)
    jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second + dt.microsecond * 1e-6)
    n = (jd + fr) - 2451545.0
    L = math.radians((280.460 + 0.9856474 * n) % 360.0)
    g = math.radians((357.528 + 0.9856003 * n) % 360.0)
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 0.0000004 * n)
    x = math.cos(lam)
    y = math.cos(eps) * math.sin(lam)
    z = math.sin(eps) * math.sin(lam)
    norm = math.sqrt(x * x + y * y + z * z)
    return (x / norm, y / norm, z / norm)


def in_earth_shadow(r, dt):
    sun = sun_unit_approx(dt)
    proj = r[0] * sun[0] + r[1] * sun[1] + r[2] * sun[2]
    if proj >= 0:
        return False
    rx = r[0] - proj * sun[0]
    ry = r[1] - proj * sun[1]
    rz = r[2] - proj * sun[2]
    miss = math.sqrt(rx * rx + ry * ry + rz * rz)
    return miss < EARTH_KM + 80.0


def in_saa(lat, lon):
    return (-50.0 <= lat <= 0.0) and (-90.0 <= lon <= 10.0)


def sample_track(sat, start, end, step_minutes=10):
    points = []
    sunlit = 0
    shadow = 0
    saa = 0
    for t in iter_steps(start, end, timedelta(minutes=step_minutes)):
        r, v = propagate(sat, t)
        lat, lon, alt = teme_to_geodetic(r, t)
        dark = in_earth_shadow(r, t)
        saa_flag = in_saa(lat, lon)
        if dark:
            shadow += 1
        else:
            sunlit += 1
        if saa_flag:
            saa += 1
        speed = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
        points.append(
            {
                "time": t,
                "lat": round(lat, 3),
                "lon": round(lon, 3),
                "alt_km": round(alt, 1),
                "in_shadow": dark,
                "in_saa": saa_flag,
                "speed_km_s": round(speed, 3),
            }
        )
    n = max(len(points), 1)
    return {
        "points": points,
        "shadow_fraction": shadow / float(n),
        "saa_fraction": saa / float(n),
        "sunlit_fraction": sunlit / float(n),
    }
