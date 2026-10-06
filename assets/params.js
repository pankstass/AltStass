/* Схема сетевых параметров и вычисление производных значений.
   Используется и в браузере (window.NET), и при сборке (node). */
(function (root) {
  var GROUPS = [
    { id: "common", title: "Общие", fields: [
      ["DOMAIN", "Домен", "au-team.irpo", "host"],
      ["PW", "Пароль (учётки, OSPF, БД)", "P@ssw0rd", "text"],
      ["TZ", "Часовой пояс", "Europe/Moscow", "text"],
      ["DNS_FWD", "DNS пересылки", "77.88.8.7", "ip"],
      ["SSH_PORT", "Порт SSH", "2027", "port"],
      ["SSH_UID", "UID sshuser", "2027", "int"],
      ["BANNER", "Баннер SSH", "Authorized access only", "text"]
    ]},
    { id: "vlan", title: "VLAN", fields: [
      ["V_SRV", "VLAN серверов", "100", "vlan"],
      ["V_CLI", "VLAN клиентов", "200", "vlan"],
      ["V_MGMT", "VLAN управления", "999", "vlan"]
    ]},
    { id: "isp", title: "ISP", fields: [
      ["ISP_WAN", "Интерфейс в Интернет (DHCP)", "enp0s3", "if"],
      ["ISP_HQ_IF", "Интерфейс к HQ-RTR", "enp0s9", "if"],
      ["ISP_HQ", "Адрес к HQ-RTR", "172.16.1.1/28", "cidr"],
      ["ISP_BR_IF", "Интерфейс к BR-RTR", "enp0s10", "if"],
      ["ISP_BR", "Адрес к BR-RTR", "172.16.2.1/28", "cidr"]
    ]},
    { id: "hqrtr", title: "HQ-RTR", fields: [
      ["HQ_WAN_IF", "Интерфейс к ISP", "enp0s10", "if"],
      ["HQ_WAN_IP", "Адрес к ISP", "172.16.1.2", "ip"],
      ["HQ_LAN_IF", "Trunk-интерфейс", "enp0s9", "if"],
      ["HQ_GW_SRV", "Шлюз VLAN серверов", "10.0.100.1/24", "cidr"],
      ["HQ_GW_CLI", "Шлюз VLAN клиентов", "10.0.200.1/24", "cidr"],
      ["HQ_GW_MGMT", "Шлюз VLAN управления", "10.0.99.1/24", "cidr"],
      ["GRE_HQ", "Адрес gre1", "10.10.10.1/30", "cidr"]
    ]},
    { id: "hqhosts", title: "HQ-SRV / HQ-CLI / DHCP", fields: [
      ["HQ_SRV_IF", "HQ-SRV: интерфейс", "enp0s9", "if"],
      ["HQ_SRV_IP", "HQ-SRV: адрес", "10.0.100.20", "ip"],
      ["HQ_CLI_IF", "HQ-CLI: интерфейс", "enp0s9", "if"],
      ["HQ_CLI_IP", "HQ-CLI: адрес (резерв)", "10.0.200.30", "ip"],
      ["HQ_CLI_MAC", "HQ-CLI: MAC", "08:00:27:ee:f2:7c", "mac"],
      ["DHCP_FROM", "Пул DHCP: от", "10.0.200.50", "ip"],
      ["DHCP_TO", "Пул DHCP: до", "10.0.200.150", "ip"]
    ]},
    { id: "br", title: "BR-RTR / BR-SRV", fields: [
      ["BR_WAN_IF", "BR-RTR: интерфейс к ISP", "enp0s9", "if"],
      ["BR_WAN_IP", "BR-RTR: адрес к ISP", "172.16.2.2", "ip"],
      ["BR_LAN_IF", "BR-RTR: trunk-интерфейс", "enp0s10", "if"],
      ["BR_GW_SRV", "BR-RTR: шлюз VLAN серверов", "10.1.100.1/28", "cidr"],
      ["BR_GW_MGMT", "BR-RTR: шлюз VLAN управления", "10.1.99.1/28", "cidr"],
      ["GRE_BR", "BR-RTR: адрес gre1", "10.10.10.2", "ip"],
      ["BR_SRV_IF", "BR-SRV: интерфейс", "enp0s9", "if"],
      ["BR_SRV_IP", "BR-SRV: адрес", "10.1.100.10", "ip"],
      ["BR_FW_IP", "BR-FW: адрес (для DNS)", "10.1.99.2", "ip"]
    ]},
    { id: "mgmt", title: "Сеть управления (Host-Only)", fields: [
      ["MG_IF", "Интерфейс", "enp0s8", "if"],
      ["MG_PFX", "Префикс", "24", "pfx"],
      ["MG_ISP", "ISP", "192.168.56.40", "ip"],
      ["MG_HQRTR", "HQ-RTR", "192.168.56.10", "ip"],
      ["MG_HQSRV", "HQ-SRV", "192.168.56.20", "ip"],
      ["MG_HQCLI", "HQ-CLI", "192.168.56.30", "ip"],
      ["MG_BRRTR", "BR-RTR", "192.168.56.50", "ip"],
      ["MG_BRSRV", "BR-SRV", "192.168.56.60", "ip"]
    ]},
    { id: "m2", title: "Модуль 2", fields: [
      ["RAID_D1", "HQ-SRV: диск 1 для RAID", "/dev/sdb", "path"],
      ["RAID_D2", "HQ-SRV: диск 2 для RAID", "/dev/sdc", "path"],
      ["ISO_DEV", "Привод с Additional.iso", "/dev/sr0", "path"],
      ["NTP_UP", "Вышестоящий NTP для ISP", "ntp1.vniiftri.ru", "host"],
      ["HQ_USERS", "Число пользователей hquser", "5", "int"],
      ["APP_PORT", "Порт testapp на BR-SRV", "8080", "port"],
      ["WEB_PORT", "Порт apache на HQ-SRV", "80", "port"],
      ["EXT_PORT", "Внешний порт веб-приложений", "8080", "port"]
    ]}
  ];

  var FIELDS = {};
  GROUPS.forEach(function (g) { g.fields.forEach(function (f) {
    FIELDS[f[0]] = { key: f[0], label: f[1], def: f[2], type: f[3], group: g.id };
  }); });

  function defaults() { var o = {}; for (var k in FIELDS) o[k] = FIELDS[k].def; return o; }

  var RE = {
    ip: /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/,
    if: /^[A-Za-z0-9_.:-]{1,15}$/,
    mac: /^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$/,
    host: /^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$/,
    path: /^\/[A-Za-z0-9_\/.-]+$/
  };
  function ip2n(s) { return s.split(".").reduce(function (a, o) { return a * 256 + (+o); }, 0); }
  function n2ip(n) { return [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255].join("."); }
  function maskN(p) { return p === 0 ? 0 : ((0xFFFFFFFF << (32 - p)) >>> 0); }
  function netOf(ip, p) { return (ip2n(ip) & maskN(p)) >>> 0; }
  function inNet(ip, cidr) { var c = cidr.split("/"); return netOf(ip, +c[1]) === netOf(c[0], +c[1]); }

  function checkField(f, v) {
    v = String(v).trim();
    if (!v) return "пустое значение";
    switch (f.type) {
      case "ip": return RE.ip.test(v) ? "" : "нужен IPv4-адрес";
      case "cidr": var c = v.split("/");
        return c.length === 2 && RE.ip.test(c[0]) && /^\d+$/.test(c[1]) && +c[1] >= 1 && +c[1] <= 30 ? "" : "формат 10.0.0.1/24";
      case "pfx": return /^\d+$/.test(v) && +v >= 1 && +v <= 30 ? "" : "число 1–30";
      case "if": return RE.if.test(v) ? "" : "имя интерфейса";
      case "vlan": return /^\d+$/.test(v) && +v >= 1 && +v <= 4094 ? "" : "число 1–4094";
      case "port": return /^\d+$/.test(v) && +v >= 1 && +v <= 65535 ? "" : "порт 1–65535";
      case "int": return /^\d+$/.test(v) && +v >= 1 && +v <= 60000 ? "" : "целое число";
      case "mac": return RE.mac.test(v) ? "" : "формат 08:00:27:aa:bb:cc";
      case "host": return RE.host.test(v) ? "" : "доменное имя";
      case "path": return RE.path.test(v) ? "" : "путь вида /dev/sdb";
      default: return /['"`$\\]/.test(v) ? "без кавычек, $ и \\" : "";
    }
  }

  /* Возвращает {errors:{key:msg}, global:[...], warnings:[...]} */
  function validate(p) {
    var errors = {}, global = [], warnings = [];
    for (var k in FIELDS) { var m = checkField(FIELDS[k], p[k]); if (m) errors[k] = m; }
    if (Object.keys(errors).length) return { errors: errors, global: global, warnings: warnings };
    function need(cond, msg, keys) { if (!cond) { global.push(msg); (keys || []).forEach(function (x) { errors[x] = errors[x] || "см. ниже"; }); } }
    need(inNet(p.HQ_WAN_IP, p.ISP_HQ), "Адрес HQ-RTR к ISP не входит в сеть " + p.ISP_HQ, ["HQ_WAN_IP"]);
    need(inNet(p.BR_WAN_IP, p.ISP_BR), "Адрес BR-RTR к ISP не входит в сеть " + p.ISP_BR, ["BR_WAN_IP"]);
    need(inNet(p.GRE_BR, p.GRE_HQ), "Адрес gre1 BR-RTR не входит в сеть туннеля " + p.GRE_HQ, ["GRE_BR"]);
    need(inNet(p.HQ_SRV_IP, p.HQ_GW_SRV), "HQ-SRV не входит в сеть VLAN серверов", ["HQ_SRV_IP"]);
    need(inNet(p.HQ_CLI_IP, p.HQ_GW_CLI), "HQ-CLI не входит в сеть VLAN клиентов", ["HQ_CLI_IP"]);
    need(inNet(p.BR_SRV_IP, p.BR_GW_SRV), "BR-SRV не входит в сеть VLAN серверов BR", ["BR_SRV_IP"]);
    need(inNet(p.DHCP_FROM, p.HQ_GW_CLI) && inNet(p.DHCP_TO, p.HQ_GW_CLI), "Пул DHCP должен лежать в сети VLAN клиентов", ["DHCP_FROM", "DHCP_TO"]);
    need(ip2n(p.DHCP_FROM) <= ip2n(p.DHCP_TO), "Начало пула DHCP больше конца", ["DHCP_FROM", "DHCP_TO"]);
    var gw = ip2n(p.HQ_GW_CLI.split("/")[0]);
    need(!(gw >= ip2n(p.DHCP_FROM) && gw <= ip2n(p.DHCP_TO)), "Адрес маршрутизатора нужно исключить из пула DHCP", ["DHCP_FROM", "DHCP_TO"]);
    need(new Set([p.V_SRV, p.V_CLI, p.V_MGMT]).size === 3, "Номера VLAN должны различаться", ["V_SRV", "V_CLI", "V_MGMT"]);
    var c = ip2n(p.HQ_CLI_IP);
    if (c >= ip2n(p.DHCP_FROM) && c <= ip2n(p.DHCP_TO)) warnings.push("Резерв HQ-CLI попадает в пул DHCP — лучше вынести его за пределы пула.");
    if (+p.HQ_GW_SRV.split("/")[1] < 24 || +p.BR_GW_SRV.split("/")[1] < 24) warnings.push("Обратные зоны DNS строятся по первым трём октетам: при маске короче /24 проверьте их вручную.");
    return { errors: errors, global: global, warnings: warnings };
  }

  /* Соответствие требованиям КИМ (размеры сетей) */
  function kim(p) {
    function pf(c) { return +c.split("/")[1]; }
    function size(x) { return Math.pow(2, 32 - x); }
    return [
      ["VLAN серверов HQ — не более 32 адресов", pf(p.HQ_GW_SRV) >= 27, "/" + pf(p.HQ_GW_SRV) + " = " + size(pf(p.HQ_GW_SRV))],
      ["VLAN клиентов HQ — не более 16 адресов", pf(p.HQ_GW_CLI) >= 28, "/" + pf(p.HQ_GW_CLI) + " = " + size(pf(p.HQ_GW_CLI))],
      ["VLAN управления — не более 8 адресов", pf(p.HQ_GW_MGMT) >= 29, "/" + pf(p.HQ_GW_MGMT) + " = " + size(pf(p.HQ_GW_MGMT))],
      ["Сеть BR-SRV — не более 16 адресов", pf(p.BR_GW_SRV) >= 28, "/" + pf(p.BR_GW_SRV) + " = " + size(pf(p.BR_GW_SRV))],
      ["Туннель — минимальная маска (/30)", pf(p.GRE_HQ) >= 30, "/" + pf(p.GRE_HQ)],
      ["Сети ISP — /28", pf(p.ISP_HQ) === 28 && pf(p.ISP_BR) === 28, "/" + pf(p.ISP_HQ) + ", /" + pf(p.ISP_BR)]
    ];
  }

  /* Пресет «маски по КИМ» */
  var KIM_PRESET = {
    HQ_GW_SRV: "10.0.100.1/27", HQ_SRV_IP: "10.0.100.20",
    HQ_GW_CLI: "10.0.200.1/28", HQ_CLI_IP: "10.0.200.14",
    DHCP_FROM: "10.0.200.2", DHCP_TO: "10.0.200.13",
    HQ_GW_MGMT: "10.0.99.1/29", BR_GW_SRV: "10.1.100.1/28", BR_SRV_IP: "10.1.100.10",
    BR_GW_MGMT: "10.1.99.1/29", BR_FW_IP: "10.1.99.2", GRE_HQ: "10.10.10.1/30", GRE_BR: "10.10.10.2"
  };

  function derive(p) {
    var d = {};
    for (var k in p) d[k] = String(p[k]).trim();
    for (var key in FIELDS) {
      var f = FIELDS[key], v = d[key];
      if (f.type === "cidr") {
        var c = v.split("/"), pf = +c[1];
        d[key + "_IP"] = c[0]; d[key + "_PFX"] = String(pf);
        d[key + "_NET"] = n2ip(netOf(c[0], pf)); d[key + "_MASK"] = n2ip(maskN(pf));
        d[key + "_SUBNET"] = d[key + "_NET"] + "/" + pf;
        d[key + "_DOT"] = "." + c[0].split(".")[3];
      } else if (f.type === "ip") {
        d[key + "_DOT"] = "." + v.split(".")[3];
      }
    }
    d.HQ_WAN_CIDR = d.HQ_WAN_IP + "/" + d.ISP_HQ_PFX;
    d.BR_WAN_CIDR = d.BR_WAN_IP + "/" + d.ISP_BR_PFX;
    d.GRE_BR_CIDR = d.GRE_BR + "/" + d.GRE_HQ_PFX;
    d.HQ_SRV_CIDR = d.HQ_SRV_IP + "/" + d.HQ_GW_SRV_PFX;
    d.HQ_CLI_CIDR = d.HQ_CLI_IP + "/" + d.HQ_GW_CLI_PFX;
    d.BR_SRV_CIDR = d.BR_SRV_IP + "/" + d.BR_GW_SRV_PFX;
    ["ISP", "HQRTR", "HQSRV", "HQCLI", "BRRTR", "BRSRV"].forEach(function (x) { d["MG_" + x + "_CIDR"] = d["MG_" + x] + "/" + d.MG_PFX; });
    function rev(ip, pre) { var o = ip.split("."); d[pre] = o[2] + "." + o[1] + "." + o[0] + ".in-addr.arpa"; d[pre + "_FILE"] = o[0] + "." + o[1] + "." + o[2] + ".rev"; d[pre + "_PTR"] = o[3]; }
    rev(d.HQ_SRV_IP, "REV_HQ"); rev(d.BR_SRV_IP, "REV_BR");
    d.REALM = d.DOMAIN.toUpperCase();
    d.WG = d.DOMAIN.split(".")[0].toUpperCase();
    d.H_ISP = "isp." + d.DOMAIN; d.H_HQRTR = "hq-rtr." + d.DOMAIN; d.H_BRRTR = "br-rtr." + d.DOMAIN;
    d.H_HQSRV = "hq-srv." + d.DOMAIN; d.H_BRSRV = "br-srv." + d.DOMAIN; d.H_HQCLI = "hq-cli." + d.DOMAIN;
    return d;
  }

  var api = { GROUPS: GROUPS, FIELDS: FIELDS, defaults: defaults, validate: validate, derive: derive, kim: kim, KIM_PRESET: KIM_PRESET };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.NET = api;
})(this);
