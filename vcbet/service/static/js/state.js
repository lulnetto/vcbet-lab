function initialLocalDate() {
  const date = new Date();
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 10);
}

const state = {
  configs: [], jobs: [], dashboard: null, selectedJobId: null,
  replayRuns: [], replaySummaries: [], replaySummaryPayload: null, replayPicks: [],
  aliasFiles: [], aliasReview: null,
  dashboardEntries: [], loadErrors: {}, lastRefreshAt: null,
  entities: { configs: [], ledgers: [], runs: [], replays: [], catalogMessages: {} },
  selectedDate: initialLocalDate(),
  selectedConfig: '',
  selectedLedger: 'official',
  selectedRun: '',
  selectedReplay: '',
  jobsPage: 1,
  jobsPageSize: 10,
};
