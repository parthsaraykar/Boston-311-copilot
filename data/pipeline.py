"""Load and clean the Boston 311 CSVs (2022 is kept only as extra forecast history), build the monthly / daily / catalog tables.

Run: python -m data.pipeline
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
OUT = ROOT / "processed"

DEPTS = {
    "PWDx": "Public Works",
    "BTDT": "Transportation",
    "PARK": "Parks",
    "ISD": "Inspectional Services",
}
CATALOG_SIZE = 170


def build(con: duckdb.DuckDBPyConnection | None = None) -> None:
    OUT.mkdir(exist_ok=True)
    con = con or duckdb.connect(str(OUT / "311.duckdb"))
    dept_map = ", ".join(f"('{k}', '{v}')" for k, v in DEPTS.items())

    con.execute(f"""
        create or replace table cases as
        with raw as (
            select * from read_csv_auto('{RAW}/311_*.csv', all_varchar=true)
        ), dm(code, dept) as (values {dept_map})
        select
            case_enquiry_id as case_id,
            try_cast(open_dt as timestamp) as open_dt,
            try_cast(closed_dt as timestamp) as closed_dt,
            try_cast(sla_target_dt as timestamp) as target_dt,
            on_time = 'ONTIME' as on_time,
            case_status = 'Closed' as is_closed,
            type, queue, department as dept_code, dm.dept,
            source,
            source = 'Employee Generated' as by_employee,
            neighborhood, pwd_district,
            try_cast(latitude as double) as lat,
            try_cast(longitude as double) as lon,
            location
        from raw left join dm on raw.department = dm.code
        where department is not null and department <> 'Test'
          and coalesce(closure_reason, '') not ilike '%duplicate%'
          and coalesce(closure_reason, '') not ilike '%invalid%'
          and try_cast(open_dt as timestamp) is not null
    """)
    end_of_data = con.execute("select max(open_dt) from cases").fetchone()[0]

    # dept x month. "30+ days late" = closed (or still open at end of data) 30+ days after SLA target.
    con.execute(f"""
        create or replace table monthly as
        select dept, date_trunc('month', open_dt)::date as month,
            count(*) as requests,
            count(*) filter (where on_time) as on_time,
            count(*) filter (where not on_time) as late,
            count(*) filter (where target_dt is not null and
                coalesce(closed_dt, timestamp '{end_of_data}') > target_dt + interval 30 day) as late_30,
            median(date_diff('hour', open_dt, closed_dt) / 24.0) as median_days_to_close,
            avg(by_employee::int) as employee_share,
            count(*) filter (where is_closed and date_trunc('month', closed_dt) = date_trunc('month', open_dt))
                as closed_same_month
        from cases where dept is not null
        group by all order by dept, month
    """)
    # closures by close month: a measure of how much work each dept actually got done
    con.execute("""
        create or replace table closures as
        select dept, date_trunc('month', closed_dt)::date as month, count(*) as closed
        from cases where dept is not null and is_closed and closed_dt is not null
        group by all order by dept, month
    """)
    con.execute("""
        create or replace table daily as
        select dept, open_dt::date as day, count(*) as requests
        from cases where dept is not null group by all order by dept, day
    """)
    # the routing catalog covers every department, not only the four planned ones
    con.execute(f"""
        create or replace table catalog as
        select row_number() over (order by count(*) desc) as id,
            type, dept_code, coalesce(dept, dept_code) as dept, queue,
            count(*) as volume_3y,
            round(count(*) / 36.0, 1) as monthly_volume,
            avg(on_time::int) as on_time_rate,
            median(date_diff('hour', open_dt, closed_dt) / 24.0) as median_days_to_close
        from cases where open_dt >= timestamp '2023-01-01'
        group by type, dept_code, dept, queue
        order by volume_3y desc limit {CATALOG_SIZE}
    """)
    con.execute("""
        create or replace table neighborhood_ontime as
        select neighborhood, dept, year(open_dt) as year, count(*) as requests,
            avg(on_time::int) as on_time_rate
        from cases where dept is not null and neighborhood is not null
        group by all
    """)
    # open cases with a location, for "similar open reports"
    con.execute(f"""
        create or replace table open_cases as
        select case_id, type, queue, dept_code, open_dt, lat, lon, location, neighborhood
        from cases
        where not is_closed and lat is not null and open_dt > timestamp '{end_of_data}' - interval 180 day
    """)

    # which queue a type goes to depends on where it is: (type, neighborhood) -> queue mix
    con.execute("""
        create or replace table type_area as
        select c.type, c.neighborhood, c.queue, c.dept_code, count(*) as n
        from cases c join catalog k using (type, dept_code, queue)
        where c.open_dt >= timestamp '2023-01-01' and c.neighborhood is not null
        group by all
    """)
    # sample of located cases: nearest-neighbour lookup from a lat/lon to neighborhood and PWD district
    con.execute("""
        create or replace table geo_points as
        select round(lat, 4) as lat, round(lon, 4) as lon, any_value(neighborhood) as neighborhood,
            any_value(pwd_district) as pwd_district
        from cases
        where lat between 42.2 and 42.45 and lon between -71.2 and -70.95 and neighborhood is not null
          and open_dt >= timestamp '2024-01-01'
        group by 1, 2
    """)

    for t in ["monthly", "closures", "daily", "catalog", "neighborhood_ontime", "open_cases", "type_area", "geo_points"]:
        con.execute(f"copy {t} to '{OUT}/{t}.parquet' (format parquet)")
        n = con.execute(f"select count(*) from {t}").fetchone()[0]
        print(f"{t:22s} {n:>8,} rows")


if __name__ == "__main__":
    build()
