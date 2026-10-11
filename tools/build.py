import html, re, json, subprocess, os, shutil
from pathlib import Path
TOOLS = Path(__file__).resolve().parent
SRC = str(TOOLS / 'src'); OUT = str(TOOLS.parent)
SITE_URL = os.environ.get('SITE_URL', 'https://USERNAME.github.io/REPO/')
D = json.loads(subprocess.check_output(['node', '-e', "const N=require(%s);console.log(JSON.stringify(N.derive(N.defaults())))" % json.dumps(SRC + '/params.js')], cwd=SRC))
TOK = re.compile(r'@([A-Z][A-Z0-9_]*)@')
E = html.escape

def tok(s, tag='span'):
    def r(m):
        k = m.group(1)
        if k not in D: raise KeyError('unknown token ' + k)
        return '<%s class="v" data-k="%s">%s</%s>' % (tag, k, E(D[k]), tag)
    return TOK.sub(r, s)
def T(s): return tok(E(s))
def plain(s): return TOK.sub(lambda m: D[m.group(1)], s)

# ---------- подсветка синтаксиса ----------
WORD = re.compile(r"'[^']*'|\"[^\"]*\"|\s+|[^\s'\"]+")
HD = re.compile(r"<<-?\s*'?([A-Za-z_]+)'?\s*$")
OPS = {'|', '&&', '||', ';', '>', '>>', '<<', '2>/dev/null', '>/dev/null'}
def seg(s, cls=None):
    e = tok(E(s))
    return '<span class="%s">%s</span>' % (cls, e) if cls else e
def hl_shell(line, cont):
    if line.lstrip().startswith('#'): return seg(line, 'c')
    out = []; first = not cont; parts = WORD.findall(line)
    for i, w in enumerate(parts):
        if w.isspace(): out.append(w); continue
        if w.startswith('#'): out.append(seg(''.join(parts[i:]), 'c')); break
        if w[0] in "'\"": out.append(seg(w, 's')); first = False
        elif w in OPS: out.append(seg(w, 'op')); first = w in ('|', '&&', '||', ';')
        elif first: out.append(seg(w, 'k')); first = w in ('for', 'while', 'if', 'sudo') and False
        elif w.startswith('-') and len(w) > 1: out.append(seg(w, 'o'))
        elif w.startswith('$'): out.append(seg(w, 'var'))
        else: out.append(seg(w))
        if (w.endswith(';') and w != ';') or w in ('do', 'then', 'else'): first = True
    return ''.join(out)
def hl_conf(line):
    s = line.strip()
    if not s: return ''
    if s.startswith(('#', '!', ';', '--')): return seg(line, 'c')
    m = re.match(r'^(\s*)([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
    if m: return m.group(1) + seg(m.group(2), 'p') + '=' + seg(m.group(3), 's')
    m = re.match(r'^(.*?)(\s;.*)$', line)
    if m: return hl_conf(m.group(1)) + seg(m.group(2), 'c')
    m = re.match(r'^(\s*)(\S+)(.*)$', line)
    return m.group(1) + seg(m.group(2), 'p') + seg(m.group(3))
def hl(code):
    out = []; hd = None; cont = False
    for line in code.split('\n'):
        if hd:
            if line.strip() == hd: out.append(seg(line, 'h')); hd = None
            else: out.append(hl_conf(line))
            continue
        out.append(hl_shell(line, cont))
        m = HD.search(line)
        if m: hd = m.group(1)
        cont = line.rstrip().endswith('\\')
    return '\n'.join(out)

# ---------- шаблоны команд ----------
def eth(i):
    return ("mkdir -p /etc/net/ifaces/%s\nprintf 'TYPE=eth\\nBOOTPROTO=static\\nDISABLED=no\\nCONFIG_IPV4=yes\\n' > /etc/net/ifaces/%s/options\n" % (i, i))
def trunk(p):
    return "mkdir -p /etc/net/ifaces/%s\nprintf 'TYPE=eth\\nBOOTPROTO=static\\nDISABLED=no\\n' > /etc/net/ifaces/%s/options\n" % (p, p)
def vlan(p, v, proto='static', extra=''):
    n = p + '.' + v
    return ("mkdir -p /etc/net/ifaces/%s\ncat > /etc/net/ifaces/%s/options << 'EOF'\nTYPE=vlan\nHOST=%s\nVID=%s\nBOOTPROTO=%s\nDISABLED=no\nCONFIG_IPV4=yes\n%sEOF\n" % (n, n, p, v, proto, extra))
MOD = "modprobe 8021q\ngrep -qx 8021q /etc/modules || echo 8021q >> /etc/modules\n"
FWD = "# IP-форвардинг\nsed -i 's/^net.ipv4.ip_forward.*/net.ipv4.ip_forward = 1/' /etc/net/sysctl.conf\nsysctl -w net.ipv4.ip_forward=1\n"
def nft(oif, pre=()):
    s = "cat > /etc/nftables/nftables.nft << 'EOF'\n#!/usr/sbin/nft -f\nflush ruleset\n\ntable ip nat {\n"
    if pre:
        s += "    chain prerouting {\n        type nat hook prerouting priority dstnat; policy accept;\n" + ''.join('        %s\n' % r for r in pre) + "    }\n\n"
    s += "    chain postrouting {\n        type nat hook postrouting priority srcnat; policy accept;\n        oifname \"%s\" masquerade\n    }\n}\nEOF\nsystemctl enable --now nftables\nsystemctl restart nftables\nnft list ruleset" % oif
    return s
def gre(local, remote, host, addr):
    return ("mkdir -p /etc/net/ifaces/gre1\ncat > /etc/net/ifaces/gre1/options << 'EOF'\nTYPE=iptun\nTUNTYPE=gre\nTUNLOCAL=%s\nTUNREMOTE=%s\nTUNTTL=255\nTUNOPTIONS='ttl 255'\nHOST=%s\nBOOTPROTO=static\nDISABLED=no\nCONFIG_IPV4=yes\nEOF\necho '%s' > /etc/net/ifaces/gre1/ipv4address\nsystemctl restart network\nip -br a show gre1" % (local, remote, host, addr))
def ospf(name, rid, nets):
    n = '\n'.join(' network %s area 0' % x for x in nets)
    return ("sed -i 's/^ospfd=no/ospfd=yes/' /etc/frr/daemons\n\ncat > /etc/frr/frr.conf << 'EOF'\nfrr defaults traditional\nhostname %s\nlog syslog informational\n!\ninterface gre1\n ip ospf network point-to-point\n ip ospf authentication message-digest\n ip ospf message-digest-key 1 md5 @PW@\n no ip ospf passive\nexit\n!\nrouter ospf\n ospf router-id %s\n passive-interface default\n%s\nexit\n!\nline vty\n!\nEOF\nsystemctl enable --now frr\nsystemctl restart frr" % (name, rid, n))

def B(devs, title, code, check=False, verified=None, expect=None): return dict(devs=devs, title=title, code=code.strip('\n'), check=check, verified=verified, expect=expect)
def S(id, num, title, exam, desc, blocks): return dict(id=id, num=num, title=title, exam=exam, desc=desc, blocks=blocks)

MG = [('ISP', 'MG_ISP'), ('HQ-RTR', 'MG_HQRTR'), ('HQ-SRV', 'MG_HQSRV'), ('HQ-CLI', 'MG_HQCLI'), ('BR-RTR', 'MG_BRRTR'), ('BR-SRV', 'MG_BRSRV')]
SOA = "@   IN SOA @H_HQSRV@. root.@DOMAIN@. ( 2027010101 12H 1H 1W 1H )\n    IN NS  @H_HQSRV@."

M1 = [
 S('prep', '0', 'Подготовка стенда', 'вне КИМ',
   'Выполняется до заданий экзамена. Сеть управления вводится вручную в консоли VirtualBox, дальше подключайтесь с хоста по SSH (<code>ssh user@192.168.56.X</code>, затем <code>su -</code>) и вставляйте блоки целиком.',
   [B([d], 'Сеть управления @MG_IF@', eth('@MG_IF@') + "echo '@%s_CIDR@' > /etc/net/ifaces/@MG_IF@/ipv4address\nsystemctl restart network" % k) for d, k in MG] + [
    B(['ISP'], 'Пакеты (пока работает NAT VirtualBox)', 'apt-get update && apt-get install -y nftables'),
    B(['HQ-RTR'], 'Пакеты', 'apt-get update && apt-get install -y frr nftables dhcp-server'),
    B(['BR-RTR'], 'Пакеты', 'apt-get update && apt-get install -y frr nftables'),
    B(['HQ-SRV'], 'Пакеты', 'apt-get update && apt-get install -y bind bind-utils openssh-server'),
    B(['BR-SRV'], 'Пакеты', 'apt-get update && apt-get install -y openssh-server'),
    B(['HQ-CLI'], 'Пакеты', 'apt-get update && apt-get install -y dhcpcd bind-utils'),
    B(['HQ-RTR', 'BR-RTR', 'HQ-SRV', 'BR-SRV', 'HQ-CLI'], 'Отключить NAT-адаптер @ISP_WAN@ (все, кроме ISP)',
      "# дальше интернет идёт только через ISP\nmkdir -p /etc/net/ifaces/@ISP_WAN@\nprintf 'TYPE=eth\\nDISABLED=yes\\nONBOOT=no\\n' > /etc/net/ifaces/@ISP_WAN@/options\nip addr flush dev @ISP_WAN@\nip link set @ISP_WAN@ down\nsystemctl restart network\nip route"),
   ]),
 S('t1', '1', 'Базовая настройка устройств', 'Задание 1',
   'Имена (FQDN), адресация внешних интерфейсов и сегмента BR, IP-форвардинг на маршрутизаторах. Адреса сегмента HQ задаются в задании 4 (VLAN).',
   [B(['ISP'], 'Имя', 'hostnamectl set-hostname @H_ISP@; exec bash'),
    B(['HQ-RTR'], 'Имя, интерфейс к ISP, форвардинг', 'hostnamectl set-hostname @H_HQRTR@\n\n' + eth('@HQ_WAN_IF@') + "echo '@HQ_WAN_CIDR@' > /etc/net/ifaces/@HQ_WAN_IF@/ipv4address\necho 'default via @ISP_HQ_IP@' > /etc/net/ifaces/@HQ_WAN_IF@/ipv4route\n\n" + FWD + 'systemctl restart network; exec bash'),
    B(['BR-RTR'], 'Имя, интерфейс к ISP, VLAN в сторону BR-SRV, форвардинг', 'hostnamectl set-hostname @H_BRRTR@\n\n' + eth('@BR_WAN_IF@') + "echo '@BR_WAN_CIDR@' > /etc/net/ifaces/@BR_WAN_IF@/ipv4address\necho 'default via @ISP_BR_IP@' > /etc/net/ifaces/@BR_WAN_IF@/ipv4route\n\n# trunk @BR_LAN_IF@ (lab-core-br): VLAN @V_SRV@ и @V_MGMT@\n" + MOD + trunk('@BR_LAN_IF@') + vlan('@BR_LAN_IF@', '@V_SRV@') + vlan('@BR_LAN_IF@', '@V_MGMT@') + "echo '@BR_GW_SRV@' > /etc/net/ifaces/@BR_LAN_IF@.@V_SRV@/ipv4address\necho '@BR_GW_MGMT@' > /etc/net/ifaces/@BR_LAN_IF@.@V_MGMT@/ipv4address\n\n" + FWD + 'systemctl restart network; exec bash\nip -br a'),
    B(['BR-SRV'], 'Имя и адрес в VLAN @V_SRV@', 'hostnamectl set-hostname @H_BRSRV@\n\n' + MOD + trunk('@BR_SRV_IF@') + vlan('@BR_SRV_IF@', '@V_SRV@') + "echo '@BR_SRV_CIDR@' > /etc/net/ifaces/@BR_SRV_IF@.@V_SRV@/ipv4address\necho 'default via @BR_GW_SRV_IP@' > /etc/net/ifaces/@BR_SRV_IF@.@V_SRV@/ipv4route\nsystemctl restart network; exec bash\nip -br a"),
    B(['HQ-SRV'], 'Имя', 'hostnamectl set-hostname @H_HQSRV@; exec bash'),
    B(['HQ-CLI'], 'Имя', 'hostnamectl set-hostname @H_HQCLI@; exec bash'),
   ]),
 S('t2', '2', 'Доступ в Интернет на ISP', 'Задание 2',
   'Внешний интерфейс получает адрес по DHCP от NAT VirtualBox (маршрут по умолчанию и DNS приходят оттуда же). Для HQ-RTR и BR-RTR — динамическая трансляция (masquerade).',
   [B(['ISP'], 'Интерфейсы и форвардинг', "mkdir -p /etc/net/ifaces/@ISP_WAN@\nprintf 'TYPE=eth\\nBOOTPROTO=dhcp\\nDISABLED=no\\nCONFIG_IPV4=yes\\n' > /etc/net/ifaces/@ISP_WAN@/options\n\n" + eth('@ISP_HQ_IF@') + "echo '@ISP_HQ@' > /etc/net/ifaces/@ISP_HQ_IF@/ipv4address\n\n" + eth('@ISP_BR_IF@') + "echo '@ISP_BR@' > /etc/net/ifaces/@ISP_BR_IF@/ipv4address\n\n" + FWD + 'systemctl restart network\nip -br a'),
    B(['ISP'], 'NAT в сторону Интернета', nft('@ISP_WAN@')),
   ]),
 S('t3', '3', 'Локальные учётные записи', 'Задание 3',
   'sshuser на серверах, net_admin на маршрутизаторах, sudo без пароля.',
   [B(['HQ-SRV', 'BR-SRV'], 'Пользователь sshuser', "id sshuser >/dev/null 2>&1 || useradd -m -u @SSH_UID@ sshuser\necho 'sshuser:@PW@' | chpasswd\nusermod -aG wheel sshuser\ngrep -q '^sshuser ' /etc/sudoers || echo 'sshuser ALL=(ALL:ALL) NOPASSWD: ALL' >> /etc/sudoers\nvisudo -c\nid sshuser"),
    B(['HQ-RTR', 'BR-RTR'], 'Пользователь net_admin', "id net_admin >/dev/null 2>&1 || useradd -m net_admin\necho 'net_admin:@PW@' | chpasswd\nusermod -aG wheel net_admin\ngrep -q '^net_admin ' /etc/sudoers || echo 'net_admin ALL=(ALL:ALL) NOPASSWD: ALL' >> /etc/sudoers\nvisudo -c\nid net_admin"),
   ]),
 S('t4', '4', 'Коммутация в сегменте HQ (VLAN)', 'Задание 4',
   'Router-on-a-stick: все VLAN маршрутизируются через один адаптер HQ-RTR (внутренняя сеть lab-core). HQ-SRV и HQ-CLI тегируют трафик сами.',
   [B(['HQ-RTR'], 'Trunk + VLAN @V_SRV@ / @V_CLI@ / @V_MGMT@', MOD + trunk('@HQ_LAN_IF@') + vlan('@HQ_LAN_IF@', '@V_SRV@') + vlan('@HQ_LAN_IF@', '@V_CLI@') + vlan('@HQ_LAN_IF@', '@V_MGMT@') + "echo '@HQ_GW_SRV@'  > /etc/net/ifaces/@HQ_LAN_IF@.@V_SRV@/ipv4address\necho '@HQ_GW_CLI@'  > /etc/net/ifaces/@HQ_LAN_IF@.@V_CLI@/ipv4address\necho '@HQ_GW_MGMT@' > /etc/net/ifaces/@HQ_LAN_IF@.@V_MGMT@/ipv4address\nsystemctl restart network\nip -br a"),
    B(['HQ-SRV'], 'VLAN @V_SRV@', MOD + trunk('@HQ_SRV_IF@') + vlan('@HQ_SRV_IF@', '@V_SRV@') + "echo '@HQ_SRV_CIDR@' > /etc/net/ifaces/@HQ_SRV_IF@.@V_SRV@/ipv4address\necho 'default via @HQ_GW_SRV_IP@' > /etc/net/ifaces/@HQ_SRV_IF@.@V_SRV@/ipv4route\nsystemctl restart network\nping -c3 @HQ_GW_SRV_IP@"),
    B(['HQ-CLI'], 'VLAN @V_CLI@ (статикой, до задания 9)', MOD + trunk('@HQ_CLI_IF@') + vlan('@HQ_CLI_IF@', '@V_CLI@', 'static', 'NM_CONTROLLED=no\n') + "echo '@HQ_CLI_CIDR@' > /etc/net/ifaces/@HQ_CLI_IF@.@V_CLI@/ipv4address\necho 'default via @HQ_GW_CLI_IP@' > /etc/net/ifaces/@HQ_CLI_IF@.@V_CLI@/ipv4route\nsystemctl restart network\nping -c3 @HQ_GW_CLI_IP@"),
   ]),
 S('t5', '5', 'Безопасный удалённый доступ (SSH)', 'Задание 5',
   'Порт, только sshuser, 2 попытки входа, баннер. После этого на серверы заходите так: <code>ssh -p @SSH_PORT@ sshuser@&lt;адрес&gt;</code>, затем <code>sudo -i</code>.',
   [B(['HQ-SRV', 'BR-SRV'], 'Настройка sshd', "echo '@BANNER@' > /etc/openssh/banner\n\nsed -i -E \\\n  -e 's/^#?Port .*/Port @SSH_PORT@/' \\\n  -e 's/^#?MaxAuthTries .*/MaxAuthTries 2/' \\\n  -e 's|^#?Banner .*|Banner /etc/openssh/banner|' \\\n  /etc/openssh/sshd_config\ngrep -q '^AllowUsers' /etc/openssh/sshd_config || echo 'AllowUsers sshuser' >> /etc/openssh/sshd_config\n\nsystemctl enable sshd\nsystemctl restart sshd\ngrep -E '^(Port|MaxAuthTries|Banner|AllowUsers)' /etc/openssh/sshd_config"),
    B(['HQ-CLI'], 'Проверка', 'ssh -p @SSH_PORT@ sshuser@@HQ_SRV_IP@\nssh -p @SSH_PORT@ sshuser@@BR_SRV_IP@   # после заданий 6–7', check=True),
   ]),
 S('t6', '6', 'IP-туннель GRE', 'Задание 6', 'Минимальная маска для двух адресов туннеля — /30.',
   [B(['HQ-RTR'], 'gre1 → BR-RTR', gre('@HQ_WAN_IP@', '@BR_WAN_IP@', '@HQ_WAN_IF@', '@GRE_HQ@')),
    B(['BR-RTR'], 'gre1 → HQ-RTR', gre('@BR_WAN_IP@', '@HQ_WAN_IP@', '@BR_WAN_IF@', '@GRE_BR_CIDR@')),
    B(['HQ-RTR'], 'Проверка', 'ping -c3 @GRE_BR@', check=True, expect='3 packets transmitted, 3 received, 0% packet loss'),
   ]),
 S('t7', '7', 'Динамическая маршрутизация OSPF', 'Задание 7',
   'FRR, area 0. Все интерфейсы пассивны, OSPF работает только на gre1. Аутентификация MD5.',
   [B(['HQ-RTR'], 'FRR / ospfd', ospf('@H_HQRTR@', '@GRE_HQ_IP@', ['@HQ_GW_SRV_SUBNET@', '@HQ_GW_CLI_SUBNET@', '@HQ_GW_MGMT_SUBNET@', '@GRE_HQ_SUBNET@'])),
    B(['BR-RTR'], 'FRR / ospfd', ospf('@H_BRRTR@', '@GRE_BR@', ['@BR_GW_SRV_SUBNET@', '@BR_GW_MGMT_SUBNET@', '@GRE_HQ_SUBNET@'])),
    B(['HQ-RTR', 'BR-RTR'], 'Проверка: сосед в состоянии Full', "vtysh -c 'show ip ospf neighbor'\nvtysh -c 'show ip route ospf'", check=True, expect='сосед в состоянии Full/-, интерфейс gre1; маршруты O>* до сетей другого офиса'),
   ]),
 S('t8', '8', 'Динамическая трансляция адресов (NAT)', 'Задание 8',
   'Masquerade в сторону ISP. Трафик между офисами идёт через gre1 и не транслируется.',
   [B(['HQ-RTR'], 'NAT → ISP (@HQ_WAN_IF@)', nft('@HQ_WAN_IF@')),
    B(['BR-RTR'], 'NAT → ISP (@BR_WAN_IF@)', nft('@BR_WAN_IF@')),
    B(['HQ-SRV', 'BR-SRV'], 'Проверка', 'ping -c3 77.88.8.8', check=True, expect='0% packet loss'),
   ]),
 S('t9', '9', 'DHCP для HQ-CLI', 'Задание 9',
   'Сервер — HQ-RTR, только на VLAN клиентов. Адрес маршрутизатора исключён из пула; HQ-CLI получает зарезервированный адрес по MAC.',
   [B(['HQ-RTR'], 'dhcpd', """cat > /etc/dhcp/dhcpd.conf << 'EOF'
option domain-name "@DOMAIN@";
option domain-name-servers @HQ_SRV_IP@;
default-lease-time 600;
max-lease-time 7200;
authoritative;

subnet @HQ_GW_CLI_NET@ netmask @HQ_GW_CLI_MASK@ {
    range @DHCP_FROM@ @DHCP_TO@;
    option routers @HQ_GW_CLI_IP@;
}

# MAC HQ-CLI: ip link show @HQ_CLI_IF@
host hq-cli {
    hardware ethernet @HQ_CLI_MAC@;
    fixed-address @HQ_CLI_IP@;
}
EOF
dhcpd -t -cf /etc/dhcp/dhcpd.conf

mkdir -p /etc/systemd/system/dhcpd.service.d
cat > /etc/systemd/system/dhcpd.service.d/override.conf << 'EOF'
[Service]
ExecStart=
ExecStart=/usr/sbin/dhcpd -f -q -cf /etc/dhcp/dhcpd.conf @HQ_LAN_IF@.@V_CLI@
EOF
systemctl daemon-reload
systemctl enable --now dhcpd
systemctl restart dhcpd
systemctl status dhcpd --no-pager"""),
    B(['HQ-CLI'], 'Перевести VLAN @V_CLI@ на DHCP', vlan('@HQ_CLI_IF@', '@V_CLI@', 'dhcp', 'NM_CONTROLLED=no\n') + "rm -f /etc/net/ifaces/@HQ_CLI_IF@.@V_CLI@/ipv4address /etc/net/ifaces/@HQ_CLI_IF@.@V_CLI@/ipv4route\nsystemctl restart network\nip -br a show @HQ_CLI_IF@.@V_CLI@\ncat /etc/resolv.conf"),
   ]),
 S('t10', '10', 'DNS (BIND на HQ-SRV)', 'Задание 10',
   'Зона и обратные зоны по таблице 3 КИМ. BIND работает в chroot <code>/var/lib/bind</code>, поэтому путь <code>/zone</code> = <code>/var/lib/bind/zone</code>.',
   [B(['HQ-SRV'], 'options.conf и зоны', """cat > /etc/bind/options.conf << 'EOF'
options {
    directory "/zone";
    pid-file none;
    listen-on { 127.0.0.1; @HQ_SRV_IP@; };
    listen-on-v6 { none; };
    allow-query { any; };
    recursion yes;
    allow-recursion { any; };
    forwarders { @DNS_FWD@; };
    forward first;
    dnssec-validation no;
};
EOF

grep -q '"@DOMAIN@"' /etc/bind/local.conf || cat >> /etc/bind/local.conf << 'EOF'
zone "@DOMAIN@" {
    type master;
    file "/zone/@DOMAIN@.zone";
};
zone "@REV_HQ@" {
    type master;
    file "/zone/@REV_HQ_FILE@";
};
zone "@REV_BR@" {
    type master;
    file "/zone/@REV_BR_FILE@";
};
EOF
named-checkconf"""),
    B(['HQ-SRV'], 'Файлы зон', """mkdir -p /var/lib/bind/zone
cat > /var/lib/bind/zone/@DOMAIN@.zone << 'EOF'
$TTL 1D
@       IN SOA  @H_HQSRV@. root.@DOMAIN@. (
                2027010101 ; serial
                12H        ; refresh
                1H         ; retry
                1W         ; expire
                1H )       ; minimum
        IN NS   @H_HQSRV@.
hq-rtr  IN A    @HQ_GW_MGMT_IP@
br-rtr  IN A    @BR_GW_MGMT_IP@
br-fw   IN A    @BR_FW_IP@
hq-srv  IN A    @HQ_SRV_IP@
hq-cli  IN A    @HQ_CLI_IP@
br-srv  IN A    @BR_SRV_IP@
docker  IN A    @ISP_HQ_IP@
web     IN A    @ISP_BR_IP@
EOF

cat > /var/lib/bind/zone/@REV_HQ_FILE@ << 'EOF'
$TTL 1D
""" + SOA + """
@REV_HQ_PTR@  IN PTR @H_HQSRV@.
EOF

cat > /var/lib/bind/zone/@REV_BR_FILE@ << 'EOF'
$TTL 1D
""" + SOA + """
@REV_BR_PTR@  IN PTR @H_BRSRV@.
EOF

chown named:named /var/lib/bind/zone/*
chmod 640 /var/lib/bind/zone/*
named-checkzone @DOMAIN@ /var/lib/bind/zone/@DOMAIN@.zone
named-checkzone @REV_HQ@ /var/lib/bind/zone/@REV_HQ_FILE@
named-checkzone @REV_BR@ /var/lib/bind/zone/@REV_BR_FILE@"""),
    B(['HQ-SRV'], 'Запуск и локальный резолвер', """sed -i 's|^#\\?CHROOT=.*|CHROOT="-t /var/lib/bind"|' /etc/sysconfig/bind
grep CHROOT /etc/sysconfig/bind
systemctl enable --now bind
systemctl restart bind

printf 'search @DOMAIN@\\nnameserver 127.0.0.1\\n' > /etc/net/ifaces/@HQ_SRV_IF@.@V_SRV@/resolv.conf
systemctl restart network"""),
    B(['HQ-SRV', 'HQ-CLI'], 'Проверка', 'dig @@HQ_SRV_IP@ @H_HQRTR@ +short\ndig @@HQ_SRV_IP@ @H_BRSRV@ +short\ndig @@HQ_SRV_IP@ -x @HQ_SRV_IP@ +short\ndig @@HQ_SRV_IP@ -x @BR_SRV_IP@ +short\ndig @@HQ_SRV_IP@ ya.ru +short', check=True, expect='@HQ_GW_MGMT_IP@, @BR_SRV_IP@, @H_HQSRV@., @H_BRSRV@., адреса ya.ru'),
   ]),
 S('t11', '11', 'Часовой пояс', 'Задание 11', 'На всех устройствах — по месту проведения экзамена.',
   [B(['Все ВМ'], 'Часовой пояс', 'timedatectl set-timezone @TZ@\ntimedatectl')]),
 S('check', '✓', 'Итоговая проверка', 'вне КИМ', 'Быстрый прогон перед сдачей.',
   [B(['HQ-CLI'], 'Связность, DNS, SSH', 'ip -br a\nip route\nping -c2 @HQ_GW_CLI_IP@\nping -c2 @HQ_SRV_IP@\nping -c2 @BR_SRV_IP@\nping -c2 77.88.8.8\nhost @H_HQSRV@\nhost ya.ru\nssh -p @SSH_PORT@ sshuser@@H_HQSRV@', check=True),
    B(['HQ-RTR', 'BR-RTR'], 'Маршрутизация и NAT', "ip -br a\nvtysh -c 'show ip ospf neighbor'\nvtysh -c 'show ip route'\nnft list ruleset\nsystemctl is-active frr nftables", check=True),
   ]),
]

ISO = "mkdir -p @ISO_DIR@\n# содержимое Additional.iso; если каталог пуст — монтируем диск\n[ -n \"$(ls -A @ISO_DIR@ 2>/dev/null)\" ] || mount @ISO_DEV@ @ISO_DIR@\n"
def chrony_client(ip):
    return "apt-get install -y chrony\nsed -i -E '/^(pool|server) /d' /etc/chrony.conf\necho 'server %s iburst' >> /etc/chrony.conf\nsystemctl enable --now chronyd\nsystemctl restart chronyd\nchronyc sources" % ip
L10, L11, L12 = 'занятие №10', 'занятие №11', 'занятие №12'
M2 = [
 S('m2t1', '1', 'Контроллер домена Samba DC', 'Задание 1',
   'Домен поднимается на BR-SRV с внутренним DNS Samba. HQ-CLI по-прежнему использует DNS HQ-SRV, поэтому на HQ-SRV добавляются SRV-записи, указывающие на контроллер. HQ-CLI вводится в домен через winbind; входить могут только члены группы <code>hq</code>, домашний каталог создаётся автоматически. Kerberos чувствителен ко времени: при ошибке <code>Clock skew</code> сначала выполните задание 4.',
   [B(['BR-SRV'], 'Установка и развёртывание домена', """apt-get update && apt-get install -y task-samba-dc
grep -q '@H_BRSRV@' /etc/hosts || echo '@BR_SRV_IP@ @H_BRSRV@ br-srv' >> /etc/hosts
rm -f /etc/samba/smb.conf
rm -rf /var/lib/samba /var/cache/samba
mkdir -p /var/lib/samba/sysvol
samba-tool domain provision --realm=@REALM@ --domain=@WG@ \\
  --server-role=dc --dns-backend=SAMBA_INTERNAL \\
  --adminpass='@PW@' --option='dns forwarder = @HQ_SRV_IP@'
cp -f /var/lib/samba/private/krb5.conf /etc/krb5.conf
systemctl enable --now samba
printf 'search @DOMAIN@\\nnameserver 127.0.0.1\\n' > /etc/net/ifaces/@BR_SRV_IF@.@V_SRV@/resolv.conf
systemctl restart network
samba-tool domain info 127.0.0.1
# внешние имена должны резолвиться через пересылку на HQ-SRV
host ya.ru 127.0.0.1"""),
    B(['BR-SRV'], 'Политика паролей, пользователи и группа hq', """samba-tool domain passwordsettings set --min-pwd-length=8 \\
  --account-lockout-threshold=5 --account-lockout-duration=30 \\
  --reset-account-lockout-after=30
samba-tool group add hq 2>/dev/null || true
for i in $(seq 1 @HQ_USERS@); do
  # пароль: @HQ_USER_PW@1, @HQ_USER_PW@2, …
  samba-tool user add hquser$i '@HQ_USER_PW@'"$i"
  samba-tool group addmembers hq hquser$i
done
samba-tool group listmembers hq
samba-tool domain passwordsettings show""",
      expect="hquser1 … hquser@HQ_USERS@ в списке группы hq; Minimum password length: 8"),
    B(['HQ-SRV'], 'SRV-записи контроллера в BIND', """if ! grep -q '^_ldap._tcp ' /var/lib/bind/zone/@DOMAIN@.zone; then
cat >> /var/lib/bind/zone/@DOMAIN@.zone << 'EOF'
_ldap._tcp               IN SRV 0 100 389  @H_BRSRV@.
_ldap._tcp.dc._msdcs     IN SRV 0 100 389  @H_BRSRV@.
_kerberos._tcp           IN SRV 0 100 88   @H_BRSRV@.
_kerberos._udp           IN SRV 0 100 88   @H_BRSRV@.
_kerberos._tcp.dc._msdcs IN SRV 0 100 88   @H_BRSRV@.
_kpasswd._tcp            IN SRV 0 100 464  @H_BRSRV@.
_kpasswd._udp            IN SRV 0 100 464  @H_BRSRV@.
_gc._tcp                 IN SRV 0 100 3268 @H_BRSRV@.
EOF
sed -i 's/2027010101 ; serial/2027010102 ; serial/' /var/lib/bind/zone/@DOMAIN@.zone
fi
named-checkzone @DOMAIN@ /var/lib/bind/zone/@DOMAIN@.zone
systemctl restart bind
dig @127.0.0.1 _ldap._tcp.@DOMAIN@ SRV +short""", expect="0 100 389 @H_BRSRV@."),
    B(['HQ-CLI'], 'Ввод в домен (winbind)', """apt-get update && apt-get install -y task-auth-ad-winbind
host -t SRV _ldap._tcp.@DOMAIN@
system-auth write ad @DOMAIN@ hq-cli @WG@ 'administrator' '@PW@'
reboot
# после перезагрузки:
# net ads testjoin && wbinfo -u | head""", verified=L10),
    B(['HQ-CLI'], 'Вход только для группы hq, sudo: cat, grep, id', """# SID группы надёжнее имени
SID=$(wbinfo --name-to-sid hq | awk '{print $1}')
echo "$SID"
cp -a /etc/security/pam_winbind.conf /etc/security/pam_winbind.conf.bak 2>/dev/null
cat > /etc/security/pam_winbind.conf << EOF
[global]
require_membership_of = $SID
mkhomedir = yes
krb5_auth = yes
krb5_ccache_type = FILE
cached_login = yes
EOF
mkdir -p /home/@REALM@ && chmod 755 /home/@REALM@
grep -q 'winbind offline logon' /etc/samba/smb.conf || sed -i '/^\\[global\\]/a winbind offline logon = yes' /etc/samba/smb.conf
testparm -s >/dev/null && systemctl restart winbind

# режим wheelonly запрещает запуск sudo всем, кроме wheel
control sudo public
echo '%hq ALL=(ALL) NOPASSWD: /bin/cat, /bin/grep, /usr/bin/id' > /etc/sudoers.d/hq
chmod 400 /etc/sudoers.d/hq
visudo -c""", verified=L10),
    B(['HQ-CLI'], 'Проверка', """wbinfo --name-to-sid hq
id hquser1
sudo -l -U hquser1
# войдите hquser1 / @HQ_USER_PW@1 через экран входа, затем в терминале:
# pwd; sudo cat /etc/hostname; sudo vi /etc/hosts""", check=True, verified=L10,
      expect="pwd → /home/@REALM@/hquser1 (создан автоматически)\nsudo cat — работает; sudo vi — «is not allowed to execute»\nпользователь не из hq — Authentication failure"),
   ]),
 S('m2t2', '2', 'Файловое хранилище RAID 0', 'Задание 2',
   'Массив md0 из двух дополнительных дисков, ext4 прямо на массиве, монтирование в <code>/raid</code> по UUID с <code>nofail</code> (система загрузится даже без массива). Имена дисков проверьте по <code>lsblk</code>.',
   [B(['HQ-SRV'], 'mdadm, файловая система, fstab', """apt-get install -y mdadm
lsblk
mdadm --zero-superblock --force @RAID_D1@ @RAID_D2@ 2>/dev/null
mdadm --create /dev/md0 --level=0 --raid-devices=2 @RAID_D1@ @RAID_D2@ --run
mkfs.ext4 -F /dev/md0
grep -q '^ARRAY /dev/md0' /etc/mdadm.conf || mdadm --detail --scan >> /etc/mdadm.conf
mkdir -p /raid
grep -q ' /raid ' /etc/fstab || printf 'UUID=%s /raid ext4 defaults,nofail 0 0\\n' "$(blkid -s UUID -o value /dev/md0)" >> /etc/fstab
systemctl daemon-reload && mount -a
cat /proc/mdstat
df -h /raid""", verified=L11),
    B(['HQ-SRV'], 'Проверка после перезагрузки', "cat /proc/mdstat\ndf -h /raid\ngrep -E 'md0|/raid' /etc/mdadm.conf /etc/fstab", check=True, verified=L11,
      expect="md0 : active raid0 …; /dev/md0 смонтирован в /raid (≈ сумма дисков)"),
   ]),
 S('m2t3', '3', 'Сервер NFS', 'Задание 3',
   'Каталог <code>/raid/nfs</code> с доступом на чтение и запись только для сети HQ-CLI; на клиенте — автомонтирование в <code>/mnt/nfs</code> (<code>_netdev,x-systemd.automount</code>).',
   [B(['HQ-SRV'], 'Экспорт /raid/nfs', """apt-get install -y nfs-server nfs-utils
mkdir -p /raid/nfs
chmod 777 /raid/nfs
grep -q '^/raid/nfs ' /etc/exports || echo '/raid/nfs @HQ_GW_CLI_SUBNET@(rw,sync,no_subtree_check)' >> /etc/exports
systemctl enable --now nfs-server
exportfs -rav
showmount -e localhost""", verified=L11),
    B(['HQ-CLI'], 'Автомонтирование', """apt-get install -y nfs-clients nfs-utils
showmount -e @HQ_SRV_IP@
mkdir -p /mnt/nfs
grep -q ' /mnt/nfs ' /etc/fstab || echo '@HQ_SRV_IP@:/raid/nfs /mnt/nfs nfs defaults,_netdev,x-systemd.automount 0 0' >> /etc/fstab
systemctl daemon-reload && mount -a
touch /mnt/nfs/probe && ls -l /mnt/nfs""", verified=L11),
    B(['HQ-SRV'], 'Проверка', 'ls -l /raid/nfs\nexportfs -v', check=True, verified=L11,
      expect="файл probe, созданный на HQ-CLI; /raid/nfs  @HQ_GW_CLI_SUBNET@(rw,…)"),
   ]),
 S('m2t4', '4', 'Служба времени chrony', 'Задание 4',
   'ISP — сервер stratum 5 (<code>minstratum 4</code> у вышестоящего источника даёт ровно 5, <code>local stratum 5</code> — на случай пропажи Интернета). Клиенты обращаются к ближайшему адресу ISP, запросы проходят через NAT маршрутизаторов.',
   [B(['ISP'], 'NTP-сервер', """apt-get install -y chrony
cat > /etc/chrony.conf << 'EOF'
server @NTP_UP@ iburst minstratum 4
local stratum 5
allow @ISP_HQ_SUBNET@
allow @ISP_BR_SUBNET@
driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
EOF
systemctl enable --now chronyd
systemctl restart chronyd
chronyc tracking | grep -i stratum""", verified=L10, expect="Stratum         : 5"),
    B(['HQ-RTR', 'HQ-SRV', 'HQ-CLI'], 'Клиент (офис HQ)', chrony_client('@ISP_HQ_IP@')),
    B(['BR-RTR', 'BR-SRV'], 'Клиент (офис BR)', chrony_client('@ISP_BR_IP@')),
    B(['ISP'], 'Проверка: клиенты видны на ISP', 'chronyc clients\nchronyc tracking | grep -i stratum', check=True,
      expect="в списке @HQ_WAN_IP@ и @BR_WAN_IP@ (клиенты за NAT); на клиентах chronyc sources — ^* @ISP_HQ_IP@ / @ISP_BR_IP@"),
   ]),
 S('m2t5', '5', 'Ansible на BR-SRV', 'Задание 5',
   'Ключи раскладываются <code>ssh-copy-id</code> по паролю, после этого <code>ansible all -m ping</code> отвечает pong без предупреждений. Порт SSH: HQ-SRV — @SSH_PORT@, HQ-CLI и маршрутизаторы — @ANS_PORT@.',
   [B(['HQ-CLI'], 'sshd и пользователь для Ansible', "apt-get install -y openssh-server python3\nid sshuser >/dev/null 2>&1 || useradd -m sshuser\necho 'sshuser:@PW@' | chpasswd\nsystemctl enable --now sshd"),
    B(['HQ-SRV', 'HQ-RTR', 'BR-RTR'], 'Python на управляемых машинах', 'apt-get install -y python3', verified=L11),
    B(['BR-SRV'], 'Ключи SSH', """apt-get install -y ansible openssh-clients
[ -f /root/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -N '' -f /root/.ssh/id_ed25519
# MaxAuthTries 2: при «Too many authentication failures» помогает PreferredAuthentications=password
O='-o StrictHostKeyChecking=accept-new -o PreferredAuthentications=password'
ssh-copy-id $O -p @SSH_PORT@ sshuser@@HQ_SRV_IP@
ssh-copy-id $O -p @ANS_PORT@ sshuser@@HQ_CLI_IP@
ssh-copy-id $O -p @ANS_PORT@ net_admin@@HQ_GW_MGMT_IP@
ssh-copy-id $O -p @ANS_PORT@ net_admin@@BR_GW_MGMT_IP@""", verified=L11),
    B(['BR-SRV'], 'Инвентарь и конфигурация', """mkdir -p /etc/ansible
cat > /etc/ansible/hosts << 'EOF'
[hq]
hq-srv ansible_host=@HQ_SRV_IP@ ansible_port=@SSH_PORT@ ansible_user=sshuser
hq-cli ansible_host=@HQ_CLI_IP@ ansible_port=@ANS_PORT@ ansible_user=sshuser
hq-rtr ansible_host=@HQ_GW_MGMT_IP@ ansible_port=@ANS_PORT@ ansible_user=net_admin

[br]
br-rtr ansible_host=@BR_GW_MGMT_IP@ ansible_port=@ANS_PORT@ ansible_user=net_admin

[all:vars]
ansible_python_interpreter=/usr/bin/python3
EOF
cat > /etc/ansible/ansible.cfg << 'EOF'
[defaults]
inventory = /etc/ansible/hosts
host_key_checking = False
deprecation_warnings = False
interpreter_python = /usr/bin/python3
EOF
cd /etc/ansible && ansible all -m ping""", verified=L11),
    B(['BR-SRV'], 'Проверка', 'ansible all -m ping', check=True, verified=L11,
      expect='4 × SUCCESS … "ping": "pong", без WARNING'),
   ]),
 S('m2t6', '6', 'Веб-приложение в Docker', 'Задание 6',
   'Образы (<code>*.tar</code>) и compose.yaml берутся с Additional.iso (<code>@ISO_DIR@</code>). Без <code>container_name</code> контейнеры получат имена вида <code>testapp-testapp-1</code> — проверяющему нужны <code>testapp</code> и <code>db</code>.',
   [B(['BR-SRV'], 'Docker и стек testapp', "apt-get install -y docker-engine docker-compose-v2\nsystemctl enable --now docker\n" + ISO + """ls @ISO_DIR@ @ISO_DIR@/docker
for f in @ISO_DIR@/docker/*.tar; do docker load -i "$f"; done
docker images
cat @ISO_DIR@/docker/readme.txt
mkdir -p /root/testapp
cp @ISO_DIR@/compose.yaml /root/testapp/ 2>/dev/null || cp @ISO_DIR@/docker/compose.yaml /root/testapp/
cd /root/testapp
# имена контейнеров testapp и db (сервисы с отступом в 2 пробела)
grep -q container_name compose.yaml || sed -i -E 's/^  (testapp|db):[[:space:]]*$/&\\n    container_name: \\1/' compose.yaml
grep -nE 'image|container_name|ports|restart|- "' compose.yaml
docker compose config -q && docker compose up -d
docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'""", verified=L12),
    B(['BR-SRV'], 'Проверка', "docker ps --format '{{.Names}} {{.Status}}'\ncurl -s -o /dev/null -w '%{http_code}\\n' http://@BR_SRV_IP@:@APP_PORT@", check=True, verified=L12,
      expect="testapp Up …, db Up …; код 200"),
   ]),
 S('m2t7', '7', 'Веб-приложение на Apache', 'Задание 7',
   'Apache + PHP + MariaDB на HQ-SRV. В <code>dump.sql</code> нет <code>CREATE DATABASE</code>, поэтому базу создают заранее; параметры подключения в <code>index.php</code> — переменные <code>$username</code>, <code>$password</code>, <code>$dbname</code>.',
   [B(['HQ-SRV'], 'LAMP и база webdb', "apt-get install -y lamp-server\nphp -m | grep -i mysqli\n" + ISO + """ls @ISO_DIR@/web
systemctl enable --now mysqld
mariadb << 'EOF'
CREATE DATABASE IF NOT EXISTS webdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'web'@'localhost' IDENTIFIED BY '@PW@';
GRANT ALL PRIVILEGES ON webdb.* TO 'web'@'localhost';
FLUSH PRIVILEGES;
EOF
mariadb webdb < @ISO_DIR@/web/dump.sql
mariadb -u web -p'@PW@' -e 'SHOW TABLES' webdb""", verified=L12),
    B(['HQ-SRV'], 'Файлы сайта и запуск', """rm -f /var/www/html/index.html
cp @ISO_DIR@/web/index.php @ISO_DIR@/web/logo.png /var/www/html/
sed -i -E \\
  -e 's/^(\\$username *= *)"[^"]*"/\\1"web"/' \\
  -e 's/^(\\$password *= *)"[^"]*"/\\1"@PW@"/' \\
  -e 's/^(\\$dbname *= *)"[^"]*"/\\1"webdb"/' \\
  /var/www/html/index.php
sed -n '2,7p' /var/www/html/index.php
systemctl enable --now httpd2
systemctl restart httpd2
curl -s http://127.0.0.1:@WEB_PORT@/ | head -20""", verified=L12),
    B(['HQ-SRV'], 'Проверка после перезагрузки', "systemctl is-active mysqld httpd2\ncurl -s -o /dev/null -w '%{http_code}\\n' http://@HQ_SRV_IP@:@WEB_PORT@/", check=True, verified=L12,
      expect="active, active; код 200, в HTML — строки таблицы из dump.sql"),
    B(['HQ-SRV'], 'Если MariaDB не запускается (ibdata1 повреждён)', """# симптом в /var/lib/mysql/log/mysqld.log: Header page consists of zero bytes in datafile: ./ibdata1
# причина — жёсткое выключение ВМ; данные пересоздаются из dump.sql
systemctl stop mysqld
mv /var/lib/mysql/db /var/lib/mysql/db.broken-$(date +%F)
mkdir /var/lib/mysql/db
chown mysql:mysql /var/lib/mysql/db && chmod 750 /var/lib/mysql/db
systemctl start mysqld
systemctl status mysqld --no-pager | head -3
# затем повторите блок «LAMP и база webdb»""", verified=L12),
   ]),
 S('m2t8', '8', 'Статическая трансляция портов', 'Задание 8',
   'Таблица nftables из задания 8 Модуля 1 дополняется цепочкой prerouting (DNAT), файл <code>/etc/nftables/nftables.nft</code> перезаписывается целиком. Условие <code>ip daddr</code> вместо <code>iifname</code> позволяет проверять проброс и из своего офиса (с HQ-CLI).',
   [B(['HQ-RTR'], 'DNAT на HQ-SRV', nft('@HQ_WAN_IF@', ['ip daddr @HQ_WAN_IP@ tcp dport @EXT_PORT@ dnat to @HQ_SRV_IP@:@WEB_PORT@', 'ip daddr @HQ_WAN_IP@ tcp dport @SSH_PORT@ dnat to @HQ_SRV_IP@:@SSH_PORT@']), verified=L12),
    B(['BR-RTR'], 'DNAT на BR-SRV', nft('@BR_WAN_IF@', ['ip daddr @BR_WAN_IP@ tcp dport @EXT_PORT@ dnat to @BR_SRV_IP@:@APP_PORT@', 'ip daddr @BR_WAN_IP@ tcp dport @SSH_PORT@ dnat to @BR_SRV_IP@:@SSH_PORT@']), verified=L12),
    B(['ISP'], 'Проверка извне', "curl -s -o /dev/null -w '%{http_code}\\n' http://@HQ_WAN_IP@:@EXT_PORT@\ncurl -s -o /dev/null -w '%{http_code}\\n' http://@BR_WAN_IP@:@EXT_PORT@\nssh -p @SSH_PORT@ sshuser@@HQ_WAN_IP@ hostname\nssh -p @SSH_PORT@ sshuser@@BR_WAN_IP@ hostname", check=True, verified=L12,
      expect="200, 200, @H_HQSRV@, @H_BRSRV@"),
    B(['HQ-CLI'], 'Проверка из офиса HQ', "curl -s -o /dev/null -w '%{http_code}\\n' http://@HQ_WAN_IP@:@EXT_PORT@\ncurl -s -o /dev/null -w '%{http_code}\\n' http://@BR_WAN_IP@:@EXT_PORT@", check=True, verified=L12,
      expect="200, 200 (при iifname первая проверка не проходила бы)"),
   ]),
 S('m2t9', '9', 'Яндекс Браузер на HQ-CLI', 'Задание 9', 'Пакет есть в репозитории ALT; другой вариант — «Центр приложений». Для отчёта нужен скриншот запущенного окна.',
   [B(['HQ-CLI'], 'Установка', 'apt-get update && apt-get install -y yandex-browser-stable\nyandex-browser-stable --version', verified=L12, expect="Yandex Browser 25.x")]),
]

DEV = {'ISP': 'isp', 'HQ-RTR': 'hq', 'HQ-SRV': 'hq', 'HQ-CLI': 'hq', 'BR-RTR': 'br', 'BR-SRV': 'br', 'Все ВМ': 'all'}
DEVS = ['ISP', 'HQ-RTR', 'HQ-SRV', 'HQ-CLI', 'BR-RTR', 'BR-SRV']

def render_steps(steps):
    toc, body = [], []
    for s in steps:
        toc.append('<li><a href="#%s" data-step="%s"><span class="n">%s</span><span class="tt">%s</span><span class="cnt" data-cnt="%s"></span></a></li>' % (s['id'], s['id'], s['num'], T(s['title']), s['id']))
        bl = []
        for i, b in enumerate(s['blocks']):
            bid = '%s-%d' % (s['id'], i + 1)
            badges = ''.join('<span class="dev d-%s">%s</span>' % (DEV[d], E(d)) for d in b['devs'])
            kind = (' chk' if b['check'] else '') + (' vf' if b['verified'] else '')
            vf = '<span class="vbadge" title="Выполнено на стенде автора: %s">✓ стенд</span>' % E(b['verified']) if b['verified'] else ''
            exp = '<div class="exp"><span class="expl">Ожидается</span><div class="expt">%s</div></div>' % T(b['expect']) if b['expect'] else ''
            bl.append('''<div class="block%s" id="%s" data-dev="%s" data-kind="%s">
<div class="bh"><label class="done" title="Отметить как выполненное"><input type="checkbox" aria-label="Готово: %s"><span class="box" aria-hidden="true"></span></label><div class="bt">%s<span class="btitle">%s</span>%s</div><button class="copy" type="button">Копировать</button></div>
<pre><code>%s</code></pre>%s</div>''' % (kind, bid, E('|'.join(b['devs'])), 'check' if b['check'] else 'cmd', E(plain(b['title'])), badges, T(b['title']), vf, hl(b['code']), exp))
        body.append('''<section class="step" id="%s" data-num="%s" data-title="%s">
<div class="sh"><span class="snum">%s</span><div><div class="exam">%s</div><h3>%s</h3></div></div>
<p class="sd">%s</p>
%s
</section>''' % (s['id'], E(s['num']), E(plain(s['title'])), s['num'], E(s['exam']), T(s['title']), tok(s['desc']), ''.join(bl)))
    return '\n'.join(toc), '\n'.join(body)

def render_docs(path):
    s = open(path, encoding='utf-8').read()
    parts = re.split(r'(<svg.*?</svg>)', s, flags=re.S)
    return ''.join(tok(p, 'tspan') if p.startswith('<svg') else tok(p) for p in parts)

def doc_toc(pairs): return '\n'.join('<li><a href="#%s"><span class="n">·</span><span class="tt">%s</span></a></li>' % p for p in pairs)

SHELL = open(SRC + '/shell.html', encoding='utf-8').read()
def page(fname, pid, title, h1, lead, docs, dtoc, steps, other):
    mod = '1' if pid == 'm1' else '2'
    for st in steps:
        m = re.match(r'^Задание (\d+)$', st['exam'])
        if m: st['exam'] = 'Задание %s · пункт %s' % (mod, m.group(1))
    toc, body = render_steps(steps)
    filt = ''.join('<button type="button" data-f="%s" aria-pressed="false">%s</button>' % (d, d) for d in DEVS)
    out = SHELL
    for k, v in {'PAGE_ID': pid, 'TITLE': title, 'H1': h1, 'LEAD': lead, 'DOCS': docs, 'DOC_TOC': dtoc, 'TOC': toc, 'STEPS': body,
                 'FILTER': filt, 'SITE_URL': SITE_URL, 'OG_URL': SITE_URL + ('' if fname == 'index.html' else fname),
                 'M1_CUR': 'aria-current="page"' if pid == 'm1' else '', 'M2_CUR': 'aria-current="page"' if pid == 'm2' else ''}.items():
        out = out.replace('{{%s}}' % k, v)
    open(os.path.join(OUT, fname), 'w', encoding='utf-8').write(out)
    return len(out)

os.makedirs(OUT + '/assets', exist_ok=True)
for f in ('params.js', 'app.js', 'style.css'): shutil.copy(SRC + '/' + f, OUT + '/assets/' + f)
n1 = page('index.html', 'm1', 'Модуль 1. Настройка сетевой инфраструктуры · стенд au-team.irpo', '<em>Модуль 1</em> Настройка сетевой инфраструктуры',
          'Документация сети и команды настройки — в порядке пунктов Задания 1 КИМ 09.02.06-1-2027 (профильный уровень).',
          render_docs(SRC + '/docs_m1.html'),
          doc_toc([('topology', 'Топология'), ('vms', 'Виртуальные машины'), ('addr', 'IP-адресация'), ('vlan', 'VLAN и подсети'), ('services', 'Службы и учётки'), ('dns', 'DNS-записи')]), M1, 'm2')
n2 = page('module2.html', 'm2', 'Модуль 2. Организация сетевого администрирования · стенд au-team.irpo', '<em>Модуль 2</em> Организация сетевого администрирования',
          'Команды в порядке пунктов Задания 2 КИМ 09.02.06-1-2027: домен, хранилище, NFS, время, Ansible, Docker, веб-приложения, проброс портов.',
          render_docs(SRC + '/docs_m2.html'), doc_toc([('needs', 'Подготовка'), ('services', 'Службы Модуля 2')]), M2, 'm1')
print('ok', n1, n2, sum(len(s['blocks']) for s in M1), sum(len(s['blocks']) for s in M2))
