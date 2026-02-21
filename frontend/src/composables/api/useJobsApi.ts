import useApi from "./useApi";

export default function useJobsApi() {
    const { client } = useApi();

    const getJobs = async () => {
        return await client.GET('/api/jobs/');
    }

    const getJob = async (jobId: string) => {
        return await client.GET('/api/jobs/{job_id}', {
            params: {
                path: {
                    job_id: jobId
                }
            }
        });
    }

    const getJobRuns = async (jobId: string) => {
        return await client.GET('/api/jobs/{job_id}/runs', {
            params: {
                path: {
                    job_id: jobId
                }
            }
        });
    }

    const getJobRun = async (jobId: string, runId: string) => {
        return await client.GET('/api/jobs/{job_id}/runs/{run_id}', {
            params: {
                path: {
                    job_id: jobId,
                    run_id: runId
                }
            }
        });
    }

    const getJobRunLogs = async (jobId: string, runId: string) => {
        return await client.GET('/api/jobs/{job_id}/runs/{run_id}/logs', {
            params: {
                path: {
                    job_id: jobId,
                    run_id: runId
                }
            }
        });
    }

    const triggerJob = async (jobId: string) => {
        return await client.POST('/api/jobs/{job_id}/trigger', {
            params: {
                path: {
                    job_id: jobId
                }
            }
        });
    }

    return {
        getJobs,
        getJob,
        getJobRuns,
        getJobRun,
        getJobRunLogs,
        triggerJob,
    }
}