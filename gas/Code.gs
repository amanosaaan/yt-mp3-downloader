/**
 * ジム体組成記録 — Google Apps Script バックエンド
 *
 * 使い方:
 *   1. https://script.google.com で新しいプロジェクトを作り、このファイルの内容を貼り付けて保存
 *      （スプレッドシートの「拡張機能 > Apps Script」から作ってもOK。その場合はそのシートに記録されます）
 *   2. 関数 setup を選んで「実行」→ 権限を承認（記録用スプレッドシートが自動作成されます）
 *   3. デプロイ > 新しいデプロイ > 種類「ウェブアプリ」
 *        次のユーザーとして実行: 自分 / アクセスできるユーザー: 全員
 *   4. 表示されたウェブアプリURL（.../exec）をフロント画面の「設定」に貼り付け
 */

// 合言葉（任意）。設定するとフロント側で同じ合言葉を入れないと読み書きできません。
const TOKEN = '';

const SHEET_NAME = '記録';
const HEADERS = ['id', '日付', '身長(cm)', '体重(kg)', '体脂肪率(%)', '骨格筋量(kg)', '内臓脂肪レベル', 'BMI', 'メモ', '登録日時'];
const FIELDS = ['id', 'date', 'height', 'weight', 'bodyFat', 'muscle', 'visceral', 'bmi', 'memo', 'createdAt'];

function setup() {
  const sh = getSheet_();
  Logger.log('記録用スプレッドシート: ' + sh.getParent().getUrl());
}

function doGet(e) {
  return handle_(() => {
    const p = (e && e.parameter) || {};
    checkToken_(p.token);
    if (p.action === 'list') return { records: listRecords_() };
    return { ok: true, sheetUrl: getSheet_().getParent().getUrl() };
  });
}

function doPost(e) {
  return handle_(() => {
    const body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    checkToken_(body.token);
    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    try {
      if (body.action === 'add') return { record: addRecord_(body.record || {}) };
      if (body.action === 'update') return { record: updateRecord_(body.record || {}) };
      if (body.action === 'delete') return { deleted: deleteRecord_(body.id) };
      throw new Error('unknown action');
    } finally {
      lock.releaseLock();
    }
  });
}

function handle_(fn) {
  let out;
  try {
    out = Object.assign({ ok: true }, fn());
  } catch (err) {
    out = { ok: false, error: String(err && err.message ? err.message : err) };
  }
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}

function checkToken_(token) {
  if (TOKEN && token !== TOKEN) throw new Error('合言葉が違います');
}

function getSheet_() {
  let ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) {
    const props = PropertiesService.getScriptProperties();
    const id = props.getProperty('SPREADSHEET_ID');
    if (id) {
      ss = SpreadsheetApp.openById(id);
    } else {
      ss = SpreadsheetApp.create('ジム体組成記録');
      props.setProperty('SPREADSHEET_ID', ss.getId());
    }
  }
  let sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME, 0);
    sh.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight('bold');
    sh.setFrozenRows(1);
    sh.getRange('B:B').setNumberFormat('yyyy-mm-dd');
    sh.getRange('J:J').setNumberFormat('yyyy-mm-dd hh:mm');
    const blank = ss.getSheets().filter(s => s.getName() !== SHEET_NAME && s.getLastRow() === 0);
    blank.forEach(s => ss.deleteSheet(s));
  }
  return sh;
}

function num_(v) {
  if (v === '' || v === null || v === undefined) return '';
  const n = Number(v);
  return isFinite(n) ? n : '';
}

function toRow_(r, id, createdAt) {
  const height = num_(r.height);
  const weight = num_(r.weight);
  const bmi = height && weight ? Math.round(weight / Math.pow(height / 100, 2) * 10) / 10 : '';
  const date = /^\d{4}-\d{2}-\d{2}$/.test(r.date || '') ? r.date : Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
  return [id, date, height, weight, num_(r.bodyFat), num_(r.muscle), num_(r.visceral), bmi, String(r.memo || '').slice(0, 500), createdAt];
}

function fromRow_(row, tz) {
  const o = {};
  FIELDS.forEach((f, i) => { o[f] = row[i]; });
  if (isDate_(o.date)) o.date = Utilities.formatDate(o.date, tz, 'yyyy-MM-dd');
  if (isDate_(o.createdAt)) o.createdAt = o.createdAt.toISOString();
  o.id = String(o.id);
  return o;
}

function isDate_(v) {
  return Object.prototype.toString.call(v) === '[object Date]';
}

function listRecords_() {
  const sh = getSheet_();
  const last = sh.getLastRow();
  if (last < 2) return [];
  const tz = sh.getParent().getSpreadsheetTimeZone();
  return sh.getRange(2, 1, last - 1, HEADERS.length).getValues()
    .filter(row => row[0] !== '')
    .map(row => fromRow_(row, tz))
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : String(a.createdAt) < String(b.createdAt) ? -1 : 1));
}

function findRow_(sh, id) {
  const last = sh.getLastRow();
  if (last < 2) return -1;
  const ids = sh.getRange(2, 1, last - 1, 1).getValues();
  for (let i = 0; i < ids.length; i++) if (String(ids[i][0]) === String(id)) return i + 2;
  return -1;
}

function addRecord_(r) {
  const sh = getSheet_();
  const row = toRow_(r, Utilities.getUuid(), new Date());
  sh.appendRow(row);
  return fromRow_(row, sh.getParent().getSpreadsheetTimeZone());
}

function updateRecord_(r) {
  const sh = getSheet_();
  const rowNo = findRow_(sh, r.id);
  if (rowNo < 0) throw new Error('記録が見つかりません');
  const createdAt = sh.getRange(rowNo, 10).getValue();
  const row = toRow_(r, String(r.id), createdAt);
  sh.getRange(rowNo, 1, 1, row.length).setValues([row]);
  return fromRow_(row, sh.getParent().getSpreadsheetTimeZone());
}

function deleteRecord_(id) {
  const sh = getSheet_();
  const rowNo = findRow_(sh, id);
  if (rowNo < 0) return false;
  sh.deleteRow(rowNo);
  return true;
}
