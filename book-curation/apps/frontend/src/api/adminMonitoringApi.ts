import { api } from "./authApi";
import type {
  MonitoringRangeType,
  MonitoringResponse,
} from "../types/adminMonitoring";

const API_PREFIX = "/api";

type MonitoringQuery = {
  rangeType: MonitoringRangeType;
  startDate?: string;
  endDate?: string;
};

export const getAdminMonitoring = async (
  query: MonitoringQuery
): Promise<MonitoringResponse> => {
  const res = await api.get<MonitoringResponse>(`${API_PREFIX}/admin/monitoring`, {
    params: {
      rangeType: query.rangeType,
      startDate: query.rangeType === "CUSTOM" ? query.startDate : undefined,
      endDate: query.rangeType === "CUSTOM" ? query.endDate : undefined,
    },
  });
  return res.data;
};
