const { spawn } = require('node:child_process');
const path = require('node:path');
const readline = require('node:readline');
const { api } = require('../client');
const AsyncStorage = require('@react-native-async-storage/async-storage');

// Run explicitly in the Python CI job, which has the backend dependencies.
const contract = process.env.AURA_CONTRACT_PYTHON ? describe : describe.skip;
contract('Mobile client against Flask and SQLite', () => {
  let bridge;
  let lines;
  const pending = [];
  let stderr = '';
  const originalFetch = globalThis.fetch;
  beforeAll(async () => {
    const ready = new Promise((resolve, reject) => pending.push({ resolve, reject }));
    bridge = spawn(process.env.AURA_CONTRACT_PYTHON, [path.resolve(__dirname, '../../../../tests/support/mobile_contract_bridge.py')], {
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    bridge.stderr.on('data', chunk => { stderr += chunk; });
    bridge.on('error', error => { while (pending.length) pending.shift().reject(error); });
    bridge.on('exit', () => { while (pending.length) pending.shift().reject(new Error(stderr || 'Contract bridge exited')); });
    lines = readline.createInterface({ input: bridge.stdout });
    lines.on('line', line => {
      try { pending.shift()?.resolve(JSON.parse(line)); }
      catch (error) { while (pending.length) pending.shift().reject(error); }
    });
    await ready;
    await AsyncStorage.clear();
    await api.setServerUrl('http://contract.test/aura');
    globalThis.fetch = jest.fn((url, options = {}) => new Promise((resolve, reject) => {
      pending.push({ resolve: response => resolve({
        ok: response.status >= 200 && response.status < 300,
        status: response.status,
        json: async () => response.body,
      }), reject });
      bridge.stdin.write(JSON.stringify({ url, method: options.method, body: options.body, headers: options.headers }) + '\n');
    }));
  }, 30000);

  afterAll(async () => {
    globalThis.fetch = originalFetch;
    if (bridge && bridge.exitCode === null) {
      const exited = new Promise(resolve => bridge.once('exit', resolve));
      bridge.stdin.end();
      await exited;
    }
    lines?.close();
  });

  it('logs in, reads, rates, saves, annotates, marks read, and revokes its token', async () => {
    const login = await api.login('contract@aura.test', 'contract-password');
    expect(login.user.email).toBe('contract@aura.test');
    expect((await api.getMe()).id).toBe(login.user.id);
    const feed = await api.getPapers({ page: 1, per_page: 1 });
    expect(feed).toMatchObject({ total: 1, has_more: false });
    const id = feed.papers[0].arxiv_id;
    expect((await api.getPaper(id)).title).toBe('Contract paper');
    const askResult = await api.askPaper(id, 'What is the finding?');
    expect(askResult.answer).toBe('The contract answer.');
    await api.ratePaper(id, 5);
    expect((await api.getPapers({ filter: 'liked' })).papers[0].rating).toBe(5);
    await api.addToReadingList(id);
    expect((await api.getReadingList()).papers.map(p => p.arxiv_id)).toContain(id);
    const note = await api.addPaperNote(id, 'A contract-tested idea', 'idea');
    expect(note.note_id).toEqual(expect.any(Number));
    expect((await api.getPaperNotes(id)).notes[0].content).toContain('A contract-tested idea');
    await api.deletePaperNote(note.note_id);
    expect((await api.getPaperNotes(id)).notes).toHaveLength(0);
    const transport = globalThis.fetch;
    globalThis.fetch = jest.fn(async (...args) => {
      await transport(...args); // The server committed; the response never reached the phone.
      throw new TypeError('Network request failed');
    });
    expect((await api.addPaperNote(id, 'Survive a lost response')).status).toBe('queued_offline');
    globalThis.fetch = transport;
    await api.flushOfflineMutations();
    expect((await api.getPaperNotes(id)).notes).toHaveLength(1);
    await api.markAsRead(id);
    expect((await api.getReadingList('unread')).papers).toHaveLength(0);
    expect((await api.getReadingList('read')).papers).toHaveLength(1);
    await api.removeFromReadingList(id);
    expect((await api.getReadingList('read')).papers).toHaveLength(0);
    const devReg = await api.registerDeviceToken('ExponentPushToken[contract-test-token-12345]', 'android', 'Contract Phone');
    expect(devReg.status).toBe('ok');
    expect(devReg.device.device_token).toBe('ExponentPushToken[contract-test-token-12345]');
    const devicesList = await api.getDevices();
    expect(devicesList.devices.length).toBeGreaterThanOrEqual(1);
    const unreg = await api.unregisterDeviceToken('ExponentPushToken[contract-test-token-12345]');
    expect(unreg.unregistered).toBe(true);
    await api.logout();
    expect(api.getToken()).toBeNull();
    await expect(api.getMe()).rejects.toMatchObject({ status: 401 });
  }, 30000);
});
