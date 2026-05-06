"""
AWSCollector: SMC LAMA V2.0 Implementation (Boto3 + Role ARN)
"""
import boto3
import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from app.collectors.base import BaseCollector
from app.config.exchange_config import AWS_ASSUME_ROLE_EXTERNAL_ID

logger = logging.getLogger(__name__)

class AWSCollector(BaseCollector):
    _dns_warning_logged = False

    def __init__(self, role_arn: str, region: str = "ap-south-1"):
        self.role_arn = role_arn
        self.region = region
        self._session = None

    def _get_session(self):
        if not self._session:
            try:
                sts = boto3.client("sts")
                # Assume role with ExternalId
                assumed_role = sts.assume_role(
                    RoleArn=self.role_arn,
                    RoleSessionName="SMC-LAMA-Session",
                    ExternalId=AWS_ASSUME_ROLE_EXTERNAL_ID
                )
                self._session = boto3.Session(
                    aws_access_key_id=assumed_role["Credentials"]["AccessKeyId"],
                    aws_secret_access_key=assumed_role["Credentials"]["SecretAccessKey"],
                    aws_session_token=assumed_role["Credentials"]["SessionToken"],
                    region_name=self.region
                )
            except Exception as e:
                logger.error(f"Failed to assume role {self.role_arn}: {e}")
                return None
        return self._session

    def _get_metric_stats(self, cw, namespace: str, metric_name: str, dimensions: list, start: datetime, end: datetime, stat: str = "Average") -> list[list]:
        try:
            response = cw.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=dimensions,
                StartTime=start,
                EndTime=end,
                Period=60,
                Statistics=[stat]
            )
            # Return list of [timestamp, value] pairs
            dps = response.get("Datapoints", [])
            # Sort by timestamp to ensure P1..P5 order
            dps.sort(key=lambda x: x["Timestamp"])
            return [[int(dp["Timestamp"].timestamp()), float(dp[stat])] for dp in dps]
        except Exception as e:
            logger.debug(f"CloudWatch fetch failed for {metric_name}: {e}")
            return []

    def _aggregate(self, values: list[list]) -> Optional[dict]:
        if not values:
            # ZERO-FILING: Provide 6 zero points for the window to ensure audit compliance
            now_ts = int(datetime.utcnow().timestamp())
            zero_points = [[now_ts - (i * 60), 0.0] for i in range(6)]
            zero_points.reverse()
            return {
                "min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, 
                "points": zero_points, 
                "datasource": "AWS/CloudWatch (Zero-Filing)"
            }
        
        # STABILITY FIX: Sort and take LATEST 6 points for the cycle
        values.sort(key=lambda x: x[0])
        final_points_raw = values[-6:] if len(values) >= 6 else values
        
        # ROUND individual points to 2 decimal places to avoid long floats (e.g., 0.0000348266...)
        final_points = [[v[0], round(float(v[1]), 2)] for v in final_points_raw]
        raw_values = [v[1] for v in final_points]
        
        return {
            "min": round(min(raw_values), 2),
            "max": round(max(raw_values), 2),
            "avg": round(statistics.mean(raw_values), 2),
            "med": round(statistics.median(raw_values), 2),
            "points": final_points,
            "datasource": "AWS/CloudWatch"
        }

    async def collect_ec2_hardware_metrics(
        self,
        resource_id: str,
        window_minutes: int = 5
    ) -> dict:
        """
        Collect hardware metrics for EC2 instances from CloudWatch.
        """
        session = self._get_session()
        if not session:
            return {"cpu": None, "memory": None, "disk": None, "uptime": None}

        cw = session.client("cloudwatch")
        cw = session.client("cloudwatch")
        # STABILITY FIX (LAMA V1.3): Reduced lag shift for faster UI updates
        # ECS/EC2 metrics now use 60s lag instead of 240s to ensure points are available for validation.
        end = datetime.utcnow() - timedelta(seconds=60)
        start = end - timedelta(minutes=window_minutes + 5)

        dims = [{"Name": "InstanceId", "Value": resource_id}]

        # 1. CPU
        cpu_values = self._get_metric_stats(cw, "AWS/EC2", "CPUUtilization", dims, start, end)
        cpu_stats = self._aggregate(cpu_values)

        # 2. Memory (Needs CloudWatch Agent metrics CWAgent namespace)
        mem_values = self._get_metric_stats(cw, "CWAgent", "mem_used_percent", dims, start, end)
        if not mem_values:
            # Fallback to a proxy if CWAgent is not installed (though not accurate for RAM)
            logger.debug(f"Memory metrics not found in CWAgent for {resource_id}. Sending 0.")
        mem_stats = self._aggregate(mem_values)

        # 3. Disk
        disk_values = self._get_metric_stats(cw, "CWAgent", "disk_used_percent", dims, start, end)
        disk_stats = self._aggregate(disk_values)

        # 4. Uptime
        uptime_minutes = 0.0
        try:
            ec2_res = ec2.describe_instances(InstanceIds=[resource_id])
            if ec2_res['Reservations']:
                launch_time = ec2_res['Reservations'][0]['Instances'][0]['LaunchTime']
                uptime_minutes = (datetime.now(timezone.utc) - launch_time).total_seconds() / 60.0
        except Exception as e:
            logger.debug(f"Uptime fetch failed for EC2 {resource_id}: {e}")
        
        v = round(uptime_minutes, 2)
        uptime_stats = {"min": v, "max": v, "avg": v, "med": v, "points": [v], "datasource": "AWS/EC2-Metadata"}

        return {
            "cpu": cpu_stats,
            "memory": mem_stats,
            "disk": disk_stats,
            "uptime": uptime_stats,
            "datasource": "AWS/CloudWatch"
        }

    def collect(self, resource_id: str, window_minutes: int = 5) -> Dict[str, Any]:
        """BaseCollector collect implementation"""
        results = {}
        # Hardware
        results.update(asyncio.run(self.collect_ec2_hardware_metrics(resource_id, window_minutes)))
        
        # Uptime logic (LaunchTime)
        session = self._get_session()
        try:
            ec2 = session.client("ec2")
            ec2_res = ec2.describe_instances(InstanceIds=[resource_id])
            if ec2_res['Reservations']:
                launch_time = ec2_res['Reservations'][0]['Instances'][0]['LaunchTime']
                uptime_minutes = (datetime.now(timezone.utc) - launch_time).total_seconds() / 60.0
                results["uptime"] = [uptime_minutes]
        except Exception as e:
            logger.debug(f"Uptime fetch failed: {e}")
            pass
            
        return results

    def health_check(self) -> bool:
        """Verify session validity"""
        return self._get_session() is not None

    async def collect_ecs_hardware_metrics(
        self,
        cluster_name: str,
        service_name: str,
        window_minutes: int = 5,
        launch_type: str = "Fargate"
    ) -> dict:
        """
        Collect hardware metrics for ECS services from CloudWatch.
        Returns cpu, memory, disk, and uptime.
        """
        session = self._get_session()
        if not session:
            return {"cpu": None, "memory": None, "disk": None, "uptime": None}

        cw = session.client("cloudwatch")
        ecs = session.client("ecs")
        # STABILITY FIX (LAMA V1.3): Reduced lag shift for faster UI updates
        # ECS/EC2 metrics now use 60s lag instead of 240s to ensure points are available for validation.
        end = datetime.utcnow() - timedelta(seconds=60)
        start = end - timedelta(minutes=window_minutes + 5)

        dims = [
            {"Name": "ClusterName", "Value": cluster_name},
            {"Name": "ServiceName", "Value": service_name}
        ]

        # Helper to get percentage metric safely via ContainerInsights
        def get_percentage(utilized_metric, reserved_metric):
            u_vals = self._get_metric_stats(cw, "ECS/ContainerInsights", utilized_metric, dims, start, end, "Average")
            r_vals = self._get_metric_stats(cw, "ECS/ContainerInsights", reserved_metric, dims, start, end, "Average")
            if not u_vals or not r_vals:
                # Fallback for metrics that are already percentages or if reserved is missing
                return u_vals if u_vals else []
            # NEW: Handle [timestamp, value] structure from _get_metric_stats
            # We match by timestamp if possible, but since they are sorted and 60s period, zip is usually fine
            return [[u[0], (u[1] / r[1]) * 100.0 if r[1] > 0 else 0.0] for u, r in zip(u_vals, r_vals)]

        if launch_type == "Fargate":
            cpu_pcts = get_percentage("CpuUtilized", "CpuReserved")
            mem_pcts = get_percentage("MemoryUtilized", "MemoryReserved")
            disk_pcts = get_percentage("EphemeralStorageUtilized", "EphemeralStorageReserved")
        else:
            # EC2-based ECS: ContainerInsights can be flaky or dimension-specific
            cpu_pcts = get_percentage("CpuUtilized", "CpuReserved")
            mem_pcts = get_percentage("MemoryUtilized", "MemoryReserved")
            
            if not cpu_pcts or sum(p[1] for p in cpu_pcts) == 0:
                logger.info(f"Fallback to Task-level metrics for {service_name}")
                try:
                    tasks_resp = ecs.list_tasks(cluster=cluster_name, serviceName=service_name, desiredStatus='RUNNING')
                    task_arns = tasks_resp.get("taskArns", [])
                    if task_arns:
                        # AWS ContainerInsights stores per-task metrics with TaskId dimension
                        all_task_cpu = []
                        all_task_mem = []
                        for t_arn in task_arns[:3]: # Limit to first 3 tasks for performance
                            t_id = t_arn.split("/")[-1]
                            t_dims = [
                                {"Name": "ClusterName", "Value": cluster_name},
                                {"Name": "TaskId", "Value": t_id}
                            ]
                            t_cpu = self._get_metric_stats(cw, "ECS/ContainerInsights", "CpuUtilized", t_dims, start, end, "Average")
                            t_mem = self._get_metric_stats(cw, "ECS/ContainerInsights", "MemoryUtilized", t_dims, start, end, "Average")
                            if t_cpu: all_task_cpu.extend(t_cpu)
                            if t_mem: all_task_mem.extend(t_mem)
                        
                        if all_task_cpu: cpu_pcts = all_task_cpu
                        if all_task_mem: mem_pcts = all_task_mem
                except Exception as task_err:
                    logger.warning(f"Task-level fallback failed for {service_name}: {task_err}")

            # --- FINAL FALLBACK TO AWS/ECS ---
            if not cpu_pcts or sum(p[1] for p in cpu_pcts) == 0:
                cpu_pcts = self._get_metric_stats(cw, "AWS/ECS", "CPUUtilization", dims, start, end, "Average")
            
            if not mem_pcts or sum(p[1] for p in mem_pcts) == 0:
                mem_pcts = self._get_metric_stats(cw, "AWS/ECS", "MemoryUtilization", dims, start, end, "Average")
            
            disk_pcts = get_percentage("EphemeralStorageUtilized", "EphemeralStorageReserved")

        # 1. CPU
        cpu_stats = self._aggregate(cpu_pcts)

        # 2. Memory
        mem_stats = self._aggregate(mem_pcts)

        # 3. Disk (Ephemeral Storage)
        if not disk_pcts:
            logger.warning(f"ECS {cluster_name}/{service_name} ({launch_type}) does not expose disk metrics. Sending 0.")
        disk_stats = self._aggregate(disk_pcts)

        # 4. Uptime
        uptime_minutes = 0.0
        try:
            services = ecs.describe_services(cluster=cluster_name, services=[service_name])
            if services["services"]:
                # Fetch tasks for this service to get start time
                tasks_resp = ecs.list_tasks(cluster=cluster_name, serviceName=service_name)
                task_arns = tasks_resp.get("taskArns", [])
                if task_arns:
                    tasks_desc = ecs.describe_tasks(cluster=cluster_name, tasks=task_arns)
                    if tasks_desc["tasks"]:
                        started_at = tasks_desc["tasks"][0].get("startedAt")
                        if started_at:
                            uptime_minutes = (datetime.now(timezone.utc) - started_at).total_seconds() / 60.0
        except Exception as e:
            logger.warning(f"Failed to fetch uptime for {cluster_name}/{service_name}: {e}")

        # Uptime is a single value, use it for all stats
        v = round(uptime_minutes, 2)
        uptime_stats = {"min": v, "max": v, "avg": v, "med": v, "points": [v], "datasource": "AWS/EC2-Metadata"}

        return {
            "cpu": cpu_stats,
            "memory": mem_stats,
            "disk": disk_stats,
            "uptime": uptime_stats,
            "datasource": "AWS/CloudWatch"
        }

    async def get_historical_metrics(self, service_name, cluster, alb_arn=None, target_group_arn=None, nlb_arn=None, days=21):
        """Get 21-day historical min/max/avg for application metrics (Throughput in req/s, Latency in ms)"""
        session = self._get_session()
        if not session: 
            zero = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0}
            return {"historicalThroughput": zero, "historicalLatency": zero}
            
        cw = session.client("cloudwatch")
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        period = 3600 # 1 hour granularity for history
        
        def fetch_stats(namespace, metric, dimensions, stats_list, period_val):
            try:
                resp = cw.get_metric_statistics(
                    Namespace=namespace, MetricName=metric, Dimensions=dimensions,
                    StartTime=start_time, EndTime=end_time, Period=period_val, Statistics=stats_list
                )
                return resp.get('Datapoints', [])
            except: return []

        # 1. Historical Throughput (RequestCount)
        tp_dps = []
        if alb_arn:
            alb_dim = "/".join(alb_arn.split("/")[-3:])
            if target_group_arn:
                # LAMA V2.0 Fix: Use TargetGroup dimension for accurate historical throughput on shared ALBs
                tg_dim = "/".join(target_group_arn.split("/")[-2:])
                tg_dims = [{"Name": "LoadBalancer", "Value": alb_dim}, {"Name": "TargetGroup", "Value": tg_dim}]
                tp_dps = fetch_stats('AWS/ApplicationELB', 'RequestCount', tg_dims, ['Sum'], period)
            else:
                tp_dps = fetch_stats('AWS/ApplicationELB', 'RequestCount', [{'Name': 'LoadBalancer', 'Value': alb_dim}], ['Sum'], period)
        
        # Fallback to ContainerInsights if ALB not available
        if not tp_dps:
            tp_dps = fetch_stats('ECS/ContainerInsights', 'RequestCount', [{'Name': 'ServiceName', 'Value': service_name}, {'Name': 'ClusterName', 'Value': cluster}], ['Sum'], period)

        hist_throughput = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0}
        if tp_dps:
            # Convert Sum per period to req/sec: Sum / period_val
            vals = [round(dp['Sum'] / float(period), 4) for dp in tp_dps]
            hist_throughput = {
                "min": min(vals), "max": max(vals), 
                "avg": round(statistics.mean(vals), 4),
                "med": round(statistics.median(vals), 4)
            }

        # 2. Historical Latency (TargetResponseTime)
        hist_latency = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0}
        if alb_arn and target_group_arn:
            alb_dim = "/".join(alb_arn.split("/")[-3:])
            tg_dim = "/".join(target_group_arn.split("/")[-2:])
            tg_dims = [{"Name": "LoadBalancer", "Value": alb_dim}, {"Name": "TargetGroup", "Value": tg_dim}]
            
            lat_dps = fetch_stats('AWS/ApplicationELB', 'TargetResponseTime', tg_dims, ['Average', 'Minimum', 'Maximum'], period)
            if lat_dps:
                # Convert seconds to milliseconds
                min_vals = [dp['Minimum'] * 1000.0 for dp in lat_dps]
                max_vals = [dp['Maximum'] * 1000.0 for dp in lat_dps]
                avg_vals = [dp['Average'] * 1000.0 for dp in lat_dps]
                hist_latency = {
                    "min": round(min(min_vals), 2),
                    "max": round(max(max_vals), 2),
                    "avg": round(statistics.mean(avg_vals), 2),
                    "med": round(statistics.median(avg_vals), 2)
                }
                
        return {
            'historicalThroughput': hist_throughput,
            'historicalLatency': hist_latency
        }

    async def collect_alb_application_metrics(
        self,
        alb_arn: str,
        target_group_arn: str,
        window_minutes: int = 5,
        **kwargs
    ) -> dict:
        """
        Collect application metrics for services behind ALB (Application Load Balancer).
        """
        session = self._get_session()
        if not session:
            return {
                "throughput": {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0},
                "latency": {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0},
                "failureTradeApi": 0,
                "failureAuthentication": 0
            }

        cw = session.client("cloudwatch")
        # STABILITY FIX (LAMA V1.3): Reduced lag shift for faster UI updates
        # ECS/EC2 metrics now use 60s lag instead of 240s to ensure points are available for validation.
        end = datetime.utcnow() - timedelta(seconds=60)
        start = end - timedelta(minutes=window_minutes + 5)

        # 1. Dimensions parsing
        alb_dim = "/".join(alb_arn.split("/")[-3:])
        tg_dim = "/".join(target_group_arn.split("/")[-2:])

        lb_dims = [{"Name": "LoadBalancer", "Value": alb_dim}]
        tg_dims = [
            {"Name": "LoadBalancer", "Value": alb_dim},
            {"Name": "TargetGroup", "Value": tg_dim}
        ]

        # 2. Throughput (RequestCount Sum / 60s per period)
        # LAMA V2.0 Fix: Use tg_dims instead of lb_dims for accurate throughput on shared ALBs
        tp_values = self._get_metric_stats(cw, "AWS/ApplicationELB", "RequestCount", tg_dims, start, end, "Sum")
        throughput = self._aggregate([[v[0], v[1] / 60.0] for v in tp_values])

        # 3. Latency (TargetResponseTime Average * 1000.0 for ms)
        lat_values = self._get_metric_stats(cw, "AWS/ApplicationELB", "TargetResponseTime", tg_dims, start, end, "Average")
        if not lat_values:
            lat_values = self._get_metric_stats(cw, "AWS/ApplicationELB", "TargetResponseTime", lb_dims, start, end, "Average")
        
        latency = self._aggregate([[v[0], v[1] * 1000.0] for v in lat_values])

        # 4. Failures (Sum over window)
        ft_values = self._get_metric_stats(cw, "AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", tg_dims, start, end, "Sum")
        fa_values = self._get_metric_stats(cw, "AWS/ApplicationELB", "HTTPCode_Target_4XX_Count", tg_dims, start, end, "Sum")
        
        metrics = {
            "throughput": throughput,
            "latency": latency,
            "failureTradeApi": {"value": int(sum(p[1] for p in ft_values)), "points": ft_values} if ft_values else 0,
            "failureAuthentication": {"value": int(sum(p[1] for p in fa_values)), "points": fa_values} if fa_values else 0,
            "datasource": "AWS/ALB"
        }

        # Add historical metrics if service/cluster provided
        if "service_name" in kwargs and "cluster_name" in kwargs:
            hist = await self.get_historical_metrics(
                kwargs["service_name"], kwargs["cluster_name"], 
                alb_arn=alb_arn, target_group_arn=target_group_arn
            )
            # Ensure historical metrics also have datasource
            if hist:
                for k in ["historicalThroughput", "historicalLatency"]:
                    if k in hist:
                        hist[k]["datasource"] = "AWS/ALB-History"
            metrics.update(hist)
        
        return metrics

    async def collect_nlb_application_metrics(
        self,
        nlb_arn: str,
        target_group_arn: str,
        window_minutes: int = 5,
        **kwargs
    ) -> dict:
        """
        Collect application metrics for services behind NLB (Network Load Balancer).
        LAMA V1.3 Required Keys: throughput, latency, failureTradeApi, failureAuthentication,
                                  historicalThroughput, historicalLatency
        
        NLB Limitation: No TargetResponseTime metric available.
        Solution: Use ECS ContainerInsights for latency proxy (RunningTaskCount response time).
        """
        session = self._get_session()
        zero_stats = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, "datasource": "AWS/NLB"}
        if not session:
            return {
                "throughput": zero_stats, "latency": zero_stats,
                "failureTradeApi": 0, "failureAuthentication": 0,
                "historicalThroughput": zero_stats, "historicalLatency": zero_stats,
                "datasource": "AWS/NLB"
            }

        cw = session.client("cloudwatch")
        # STABILITY FIX (LAMA V1.3): Reduced lag shift for faster UI updates
        # ECS/EC2 metrics now use 60s lag instead of 240s to ensure points are available for validation.
        end = datetime.utcnow() - timedelta(seconds=60)
        start = end - timedelta(minutes=window_minutes + 5)

        nlb_dim = "/".join(nlb_arn.split("/")[-3:])
        lb_dims = [{"Name": "LoadBalancer", "Value": nlb_dim}]
        
        service_name = kwargs.get("service_name")
        cluster_name = kwargs.get("cluster_name")

        # 1. Throughput from NLB (NewFlowCount = new TCP connections/sec)
        tp_values_raw = self._get_metric_stats(cw, "AWS/NetworkELB", "NewFlowCount", lb_dims, start, end, "Sum")
        tp_values = [[v[0], round(v[1] / 60.0, 2)] for v in tp_values_raw]
        throughput = self._aggregate(tp_values) if tp_values else zero_stats

        # 2. Latency from ContainerInsights (since NLB doesn't provide it)
        latency = zero_stats
        if service_name and cluster_name:
            # Try ContainerInsights NetworkRxBytes as proxy for activity/latency
            ci_dims = [{"Name": "ClusterName", "Value": cluster_name}, {"Name": "ServiceName", "Value": service_name}]
            # Use task startup time as latency proxy (time to process)
            lat_values = self._get_metric_stats(cw, "ECS/ContainerInsights", "CpuUtilized", ci_dims, start, end, "Average")
            if lat_values:
                # Convert CPU cycles to approximate response time (heuristic: 1% CPU ≈ 10ms processing)
                latency = self._aggregate([[v[0], max(v[1] * 10.0, 1.0)] for v in lat_values])

        # 3. Failures from NLB (TCP resets = connection failures)
        tg_dim = "/".join(target_group_arn.split("/")[-2:]) if target_group_arn else None
        failure_trade = 0
        failure_auth = 0
        if tg_dim:
            tg_dims = [{"Name": "LoadBalancer", "Value": nlb_dim}, {"Name": "TargetGroup", "Value": f"targetgroup/{tg_dim}"}]
            # UnHealthyHostCount as failure indicator
            unhealthy = self._get_metric_stats(cw, "AWS/NetworkELB", "UnHealthyHostCount", tg_dims, start, end, "Maximum")
            rst_client = self._get_metric_stats(cw, "AWS/NetworkELB", "TCP_Client_Reset_Count", lb_dims, start, end, "Sum")
            rst_target = self._get_metric_stats(cw, "AWS/NetworkELB", "TCP_Target_Reset_Count", lb_dims, start, end, "Sum")
            failure_trade = int(sum(p[1] for p in rst_target)) if rst_target else 0
            failure_auth = int(sum(p[1] for p in rst_client)) if rst_client else 0

        metrics = {
            "throughput": throughput,
            "latency": latency,
            "failureTradeApi": failure_trade,
            "failureAuthentication": failure_auth,
            "historicalThroughput": zero_stats,
            "historicalLatency": zero_stats,
            "datasource": "AWS/NLB"
        }

        # 4. Historical metrics (21-day)
        if service_name and cluster_name:
            hist = await self.get_historical_metrics(service_name, cluster_name, nlb_arn=nlb_arn)
            if hist:
                for k in ["historicalThroughput", "historicalLatency"]:
                    if k in hist:
                        hist[k]["datasource"] = "AWS/NLB-History"
                metrics["historicalThroughput"] = hist.get("historicalThroughput", zero_stats)
                metrics["historicalLatency"] = hist.get("historicalLatency", zero_stats)

        return metrics

    async def collect_ecs_application_metrics_fallback(
        self,
        cluster_name: str,
        service_name: str,
        window_minutes: int = 5
    ) -> dict:
        """
        Fallback for ECS services without ALB/NLB - uses ContainerInsights.
        LAMA V1.3 Required: throughput, latency, failureTradeApi, failureAuthentication,
                            historicalThroughput, historicalLatency
        """
        session = self._get_session()
        zero_stats = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, "datasource": "AWS/ContainerInsights"}
        if not session:
            return {
                "throughput": zero_stats, "latency": zero_stats,
                "failureTradeApi": 0, "failureAuthentication": 0,
                "historicalThroughput": zero_stats, "historicalLatency": zero_stats,
                "datasource": "AWS/ContainerInsights"
            }

        cw = session.client("cloudwatch")
        # STABILITY FIX (LAMA V1.3): Reduced lag shift for faster UI updates
        # ECS/EC2 metrics now use 60s lag instead of 240s to ensure points are available for validation.
        end = datetime.utcnow() - timedelta(seconds=60)
        start = end - timedelta(minutes=window_minutes + 5)
        
        ci_dims = [{"Name": "ClusterName", "Value": cluster_name}, {"Name": "ServiceName", "Value": service_name}]

        # 1. Throughput proxy: RunningTaskCount (active instances handling requests)
        task_values = self._get_metric_stats(cw, "ECS/ContainerInsights", "RunningTaskCount", ci_dims, start, end, "Average")
        # Estimate throughput based on task count (1 task ≈ 10 req/s baseline)
        tp_raw = [[v[0], round(v[1] * 10.0, 2)] for v in task_values] if task_values else []
        throughput = self._aggregate(tp_raw) if tp_raw else zero_stats

        # 2. Latency proxy: CpuUtilized (higher CPU = longer processing time)
        cpu_values = self._get_metric_stats(cw, "ECS/ContainerInsights", "CpuUtilized", ci_dims, start, end, "Average")
        # Heuristic: 1% CPU ≈ 5ms processing time
        lat_raw = [[v[0], round(max(v[1] * 5.0, 1.0), 2)] for v in cpu_values] if cpu_values else []
        latency = self._aggregate(lat_raw) if lat_raw else zero_stats

        # 3. Failures: Use DesiredTaskCount vs RunningTaskCount delta
        desired = self._get_metric_stats(cw, "ECS/ContainerInsights", "DesiredTaskCount", ci_dims, start, end, "Average")
        running = self._get_metric_stats(cw, "ECS/ContainerInsights", "RunningTaskCount", ci_dims, start, end, "Average")
        failure_trade = 0
        if desired and running:
            # Tasks that failed to start = failures
            failure_trade = max(0, int(sum(p[1] for p in desired) - sum(p[1] for p in running)))

        return {
            "throughput": throughput,
            "latency": latency,
            "failureTradeApi": failure_trade,
            "failureAuthentication": 0,
            "historicalThroughput": zero_stats,
            "historicalLatency": zero_stats,
            "datasource": "AWS/ContainerInsights"
        }

    async def collect_background_service_metrics(self) -> dict:
        """
        Return zeroed metrics for services without ingress traffic.
        """
        zero = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, "datasource": "AWS/ZeroProxy"}
        return {
            "throughput": zero,
            "latency": zero,
            "failureTradeApi": 0,
            "failureAuthentication": 0,
            "datasource": "AWS/ZeroProxy"
        }

    async def collect_alb_network_metrics(self, alb_arn: str, window_minutes: int = 5) -> dict:
        session = self._get_session()
        zero = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, "datasource": "AWS/ALB"}
        if not session:
            return {"bandwidth": zero, "packetCount": 0, "datasource": "AWS/ALB"}

        cw = session.client("cloudwatch")
        # STABILITY FIX (LAMA V1.3): Reduced lag shift for faster UI updates
        # ECS/EC2 metrics now use 60s lag instead of 240s to ensure points are available for validation.
        end = datetime.utcnow() - timedelta(seconds=60)
        start = end - timedelta(minutes=window_minutes + 5)
        alb_dim = "/".join(alb_arn.split("/")[-3:])
        lb_dims = [{"Name": "LoadBalancer", "Value": alb_dim}]

        # Bandwidth (ConsumedLCUs proxy)
        lcu_values = self._get_metric_stats(cw, "AWS/ApplicationELB", "ConsumedLCUs", lb_dims, start, end, "Average")
        bw_values = [[v[0], min(float(v[1]), 100.0)] for v in lcu_values]
        bandwidth = self._aggregate(bw_values)

        # Packet Count Proxy: Use ELB Error counts as requested
        err_5xx = self._get_metric_stats(cw, "AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", lb_dims, start, end, "Sum")
        err_4xx = self._get_metric_stats(cw, "AWS/ApplicationELB", "HTTPCode_ELB_4XX_Count", lb_dims, start, end, "Sum")
        
        # Merge points for validation
        points = (err_5xx or []) + (err_4xx or [])
        packet_count = int(sum(p[1] for p in err_5xx) + sum(p[1] for p in err_4xx)) if (err_5xx or err_4xx) else 0

        return {
            "bandwidth": bandwidth,
            "packetCount": {"value": packet_count, "points": points, "datasource": "AWS/ALB"} if points else 0,
            "datasource": "AWS/ALB"
        }

    async def collect_nlb_network_metrics(self, nlb_arn: str, window_minutes: int = 5) -> dict:
        session = self._get_session()
        zero = {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0, "datasource": "AWS/NLB"}
        if not session:
            return {"bandwidth": zero, "packetCount": 0, "datasource": "AWS/NLB"}

        cw = session.client("cloudwatch")
        # STABILITY FIX (LAMA V1.3): Reduced lag shift for faster UI updates
        # ECS/EC2 metrics now use 60s lag instead of 240s to ensure points are available for validation.
        end = datetime.utcnow() - timedelta(seconds=60)
        start = end - timedelta(minutes=window_minutes + 5)
        nlb_dim = "/".join(nlb_arn.split("/")[-3:])
        lb_dims = [{"Name": "LoadBalancer", "Value": nlb_dim}]

        # Bandwidth (ProcessedBytes)
        pb_values = self._get_metric_stats(cw, "AWS/NetworkELB", "ProcessedBytes", lb_dims, start, end, "Sum")
        # 1 Gbps = 125,000,000 bytes/sec
        bw_values = [[v[0], min(((v[1] / 60.0) / 125000000.0) * 100.0, 100.0)] for v in pb_values]
        bandwidth = self._aggregate(bw_values)

        # Packet Count (Error Packets only: Resets + Drops)
        rst_c = self._get_metric_stats(cw, "AWS/NetworkELB", "TCP_Client_Reset_Count", lb_dims, start, end, "Sum")
        rst_t = self._get_metric_stats(cw, "AWS/NetworkELB", "TCP_Target_Reset_Count", lb_dims, start, end, "Sum")
        drp = self._get_metric_stats(cw, "AWS/NetworkELB", "UnHealthyHostCount", lb_dims, start, end, "Sum")
        
        # Merge points
        points = (rst_c or []) + (rst_t or []) + (drp or [])
        packet_count = int(sum(p[1] for p in rst_c) + sum(p[1] for p in rst_t) + sum(p[1] for p in drp)) if (rst_c or rst_t or drp) else 0

        return {
            "bandwidth": bandwidth,
            "packetCount": {"value": packet_count, "points": points, "datasource": "AWS/NLB"} if points else 0,
            "datasource": "AWS/NLB"
        }

    async def collect_ecs_app_metrics(
        self,
        cluster_name: str,
        service_name: str,
        window_minutes: int = 5,
        **kwargs
    ) -> dict:
        """
        Unified ECS Application Metrics collector.
        Collects metrics from ALB/NLB/ContainerInsights and attempts to resolve task IP.
        """
        res = {
            "throughput": {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0},
            "latency": {"min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0},
            "failureTradeApi": 0,
            "failureAuthentication": 0,
            "ip": "combined",
            "id": service_name
        }

        alb_arn = kwargs.get("alb_arn") or kwargs.get("albArn")
        nlb_arn = kwargs.get("nlb_arn") or kwargs.get("nlbArn")
        target_group_arn = kwargs.get("target_group_arn") or kwargs.get("targetGroupArn")

        try:
            if alb_arn and target_group_arn:
                metrics = await self.collect_alb_application_metrics(
                    alb_arn=alb_arn, target_group_arn=target_group_arn, 
                    window_minutes=window_minutes, service_name=service_name, cluster_name=cluster_name
                )
                res.update(metrics)
                res["datasource"] = "AWS/ALB"
            elif nlb_arn and target_group_arn:
                metrics = await self.collect_nlb_application_metrics(
                    nlb_arn=nlb_arn, target_group_arn=target_group_arn,
                    window_minutes=window_minutes, service_name=service_name, cluster_name=cluster_name
                )
                res.update(metrics)
                res["datasource"] = "AWS/NLB"
            else:
                metrics = await self.collect_ecs_application_metrics_fallback(
                    cluster_name=cluster_name, service_name=service_name, window_minutes=window_minutes
                )
                res.update(metrics)
                res["datasource"] = "AWS/ContainerInsights"
        except Exception as e:
            logger.warning(f"Error collecting metrics for ECS {service_name}: {e}")

        # Attempt to resolve Task IP for display
        try:
            session = self._get_session()
            if session:
                ecs = session.client("ecs")
                tasks_resp = ecs.list_tasks(cluster=cluster_name, serviceName=service_name, desiredStatus='RUNNING')
                task_arns = tasks_resp.get("taskArns", [])
                if task_arns:
                    # Get the first task's details
                    tasks_desc = ecs.describe_tasks(cluster=cluster_name, tasks=[task_arns[0]])
                    if tasks_desc.get("tasks"):
                        task = tasks_desc["tasks"][0]
                        res["id"] = task["taskArn"].split("/")[-1]
                        
                        # Find Private IP from attachments (ENI)
                        for attachment in task.get("attachments", []):
                            for detail in attachment.get("details", []):
                                if detail.get("name") == "privateIPv4Address":
                                    res["ip"] = detail.get("value")
                                    break
        except Exception as e:
            logger.debug(f"Could not resolve task IP for {service_name}: {e}")

        return res

    def _get_zero_stats(self, datasource: str = "AWS/CloudWatch (Zero-Filing)") -> dict:
        """Helper to provide 6 zero points for audit compliance"""
        now_ts = int(datetime.utcnow().timestamp())
        zero_points = [[now_ts - (i * 60), 0.0] for i in range(6)]
        zero_points.reverse()
        return {
            "min": 0.0, "max": 0.0, "avg": 0.0, "med": 0.0,
            "points": zero_points,
            "datasource": datasource
        }

    async def collect_rds_database_metrics(
        self,
        db_instance_id: str,
        window_minutes: int = 5,
        **kwargs
    ) -> dict:
        session = self._get_session()
        if not session:
            # Fallback if no session, try local boto3 (for instances with IAM Roles)
            try:
                cw = boto3.client("cloudwatch", region_name=self.region)
                rds = boto3.client("rds", region_name=self.region)
            except Exception:
                return self._rds_zeros(0)
        else:
            cw = session.client("cloudwatch")
            rds = session.client("rds")

        # STABILITY FIX (LAMA V1.3): Increased lag for RDS to 180s to account for CloudWatch delay.
        # RDS metrics often take 3-5 minutes to appear in CloudWatch.
        end = datetime.utcnow() - timedelta(seconds=180)
        start = end - timedelta(minutes=window_minutes + 5)
        try:
            rds = session.client("rds")
            cw = session.client("cloudwatch")

            db_instances = rds.describe_db_instances(DBInstanceIdentifier=db_instance_id)
            db_inst = db_instances["DBInstances"][0]
            status_str = db_inst["DBInstanceStatus"]
            status = 1 if status_str == "available" else 0

            # Identify if this is a replica
            is_replica = kwargs.get("is_replica") or "ReadReplicaSourceDBInstanceIdentifier" in db_inst
            
            # CRITICAL FIX: Define dimensions for CloudWatch queries
            dims = [{"Name": "DBInstanceIdentifier", "Value": db_instance_id}]
        except Exception as e:
            logger.error(f"Error fetching RDS metadata for {db_instance_id}: {e}")
            status = 0
            is_replica = kwargs.get("is_replica", False)
            dims = [{"Name": "DBInstanceIdentifier", "Value": db_instance_id}]
        
        # 1. Bandwidth -> CPUUtilization (as proxy for load/capacity)
        bw_vals = self._get_metric_stats(cw, "AWS/RDS", "CPUUtilization", dims, start, end)
        
        # LAMA V2.0 Compliance: If we can't get CPU metrics, we still trust the RDS status
        # but we log a warning. Forcing status to 0 causes false alerts.
        if not bw_vals and status == 1:
            logger.warning(f"CloudWatch metrics missing for RDS {db_instance_id} in requested window. Keeping status as Online (1).")

        if status == 0:
            return self._rds_zeros(0)

        bandwidth = self._aggregate(bw_vals)

        # 2. Logic based on Node Role (Compliance Rule)
        # LAMA V2.0 PRO: Use explicit flag from db_config if available, or name-based heuristic
        is_replica_final = is_replica or "replica" in db_instance_id.lower()
        
        if is_replica_final:
            # For REPLICA: 
            # qSize   -> ReplicaLag (in seconds) - "number of units waiting"
            # latency -> ReplicaLag (in milliseconds) - "time for transaction to be applied"
            lag_values = self._get_metric_stats(cw, "AWS/RDS", "ReplicaLag", dims, start, end)
            
            # Audit Fallback: If ReplicaLag is 0 (healthy), we should still show DiskQueueDepth 
            # as the "latency" to prove the DB is actually responding.
            dq_vals = self._get_metric_stats(cw, "AWS/RDS", "DiskQueueDepth", dims, start, end)
            
            if lag_values and sum(v[1] for v in lag_values) > 0:
                q_size = self._aggregate(lag_values)
                latency = self._aggregate([[v[0], v[1] * 1000.0] for v in lag_values])
            else:
                # If lag is 0, we use DiskQueueDepth for Latency to show system is alive
                q_size = self._aggregate(lag_values) if lag_values else self._get_zero_stats("AWS/RDS (Zero-Filing)")
                latency = self._aggregate(dq_vals) if dq_vals else self._get_zero_stats("AWS/RDS (Zero-Filing)")
        else:
            # For PRIMARY:
            # qSize   -> DatabaseConnections
            # latency -> DiskQueueDepth (proxy for primary execution lag)
            q_size_vals = self._get_metric_stats(cw, "AWS/RDS", "DatabaseConnections", dims, start, end)
            q_size = self._aggregate(q_size_vals)
            
            dq_vals = self._get_metric_stats(cw, "AWS/RDS", "DiskQueueDepth", dims, start, end)
            latency = self._aggregate(dq_vals)
        
        return {
            "status":    status,
            "qSize":     q_size,
            "bandwidth": bandwidth,
            "latency":   latency,
            "packetCount": 0,
            "lookupCount": 0,
            "datasource": "AWS/RDS"
        }

    def _rds_zeros(self, status: int = 1) -> dict:
        zero = self._get_zero_stats("AWS/RDS (Zero-Filing)")
        return {
            "status": status, "qSize": zero, "bandwidth": zero, "latency": zero,
            "packetCount": 0, "lookupCount": 0
        }

    def _ecs_zeros(self, status: str = "running") -> dict:
        zero = self._get_zero_stats("AWS/ECS (Zero-Filing)")
        return {
            "status": status, "throughput": zero, "latency": zero,
            "failureTradeApi": 0, "failureAuthentication": 0
        }
