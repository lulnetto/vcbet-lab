function initialLocalDate() {
  const date = new Date();
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 10);
}

const state = {
  configs: [], jobs: [], dashboard: null, selectedJobId: null,
  replayRuns: [], replaySummaries: [], replaySummaryPayload: null, replayPicks: [],
  aliasFiles: [], aliasReview: null,
  teamRegistry: { pending: [], approved: [], leagues: [], pendingByLeague: {}, approvedByLeague: {}, loading: false, syncing: false, error: '', selectedLeague: '', reviewFilter: '', syncResult: null },
  configPresets: { items: [], selectedName: '', detail: null, issues: [], message: '', loading: false },
  aliasDiagnostics: { scope: 'runs_recent', includeResolved: false },
  dashboardEntries: [], loadErrors: {}, lastRefreshAt: null,
  entities: { configs: [], ledgers: [], runs: [], replays: [], catalogMessages: {} },
  selectedDate: initialLocalDate(),
  selectedConfig: '',
  selectedLedger: 'official',
  selectedRun: '',
  selectedReplay: '',
  selectedReplayHistory: '',
  jobsPage: 1,
  jobsPageSize: 10,
};
