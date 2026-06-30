function showPage(page)
{
    document
        .querySelectorAll('.page')
        .forEach(p =>
        {
            p.classList.remove('active');
        });

    document
        .getElementById(page)
        .classList.add('active');

    document
        .querySelectorAll('[data-page-button]')
        .forEach(button =>
        {
            button.classList.toggle(
                'active',
                button.dataset.pageButton === page);
        });

    if (page === 'system')
    {
        refreshEventLog();
    }
}

const themeStorageKey = 'uNodeTheme';

function resolveThemeMode(mode)
{
    const prefersDark =
        window.matchMedia
        && window.matchMedia('(prefers-color-scheme: dark)').matches;

    return mode === 'dark'
        || (mode === 'auto' && prefersDark)
            ? 'dark'
            : 'light';
}

function applyThemeMode(mode)
{
    document.documentElement.dataset.theme =
        resolveThemeMode(mode);

    const selector =
        document.getElementById('themeMode');

    if (selector)
    {
        selector.value = mode;
    }
}

function setThemeMode(mode)
{
    localStorage.setItem(
        themeStorageKey,
        mode);

    applyThemeMode(mode);
}

function initializeTheme()
{
    const mode =
        localStorage.getItem(themeStorageKey) || 'auto';

    applyThemeMode(mode);

    if (window.matchMedia)
    {
        window
            .matchMedia('(prefers-color-scheme: dark)')
            .addEventListener(
                'change',
                () =>
                {
                    if ((localStorage.getItem(themeStorageKey) || 'auto')
                        === 'auto')
                    {
                        applyThemeMode('auto');
                    }
                });
    }
}

let authToken =
    sessionStorage.getItem('uNodeAuthToken') || '';
let authEnabled = false;
let authAuthenticated = false;
let lastKnownUniverse = null;

function isUiLocked()
{
    return authEnabled && !authAuthenticated;
}

function authHeaders(extraHeaders = {})
{
    const headers =
        Object.assign({}, extraHeaders);

    if (authToken.length > 0)
    {
        headers['X-uNode-Auth'] =
            authToken;
    }

    return headers;
}

function authenticatedFetch(url, options = {})
{
    return fetch(
        url,
        Object.assign(
            {},
            options,
            {
                headers:
                    authHeaders(options.headers || {})
            }));
}

function updateProtectedUi()
{
    const locked =
        isUiLocked();

    document
        .querySelectorAll(
            '.content input:not(#loginPassword), .content select, .content button:not(#authButton):not(#eventLogRefreshButton):not(#eventLogDownloadButton), #detectNodeButton')
        .forEach(element =>
        {
            element.disabled =
                locked;
        });

    const saveButton =
        document.getElementById(
            'saveRestartButton');

    if (saveButton)
    {
        saveButton.disabled =
            locked;
    }

    updateDmxOverrideStatus(
        dmxTestOverrideActive,
        0);

    if (lastHardwareStatus)
    {
        updateHardwareStatus(
            lastHardwareStatus);
    }

    if (document.getElementById('dhcp'))
    {
        updateIPMode();
    }

    updateOtaButtons();
}

function updateAuthButton()
{
    const button =
        document.getElementById(
            'authButton');

    const stateText =
        document.getElementById(
            'authStateText');

    const lockState =
        document.getElementById(
            'authLockState');

    const lockShackle =
        document.getElementById(
            'authLockShackle');
    const loginPassword =
        document.getElementById(
            'loginPassword');

    if (!button)
    {
        return;
    }

    button.classList.toggle(
        'unlocked',
        authEnabled && authAuthenticated);

    button.classList.toggle(
        'unconfigured',
        !authEnabled);

    if (!authEnabled)
    {
        button.textContent =
            'No Password';

        if (stateText)
        {
            stateText.textContent =
                'No password configured';
        }
    }
    else
    {
        button.textContent =
            authAuthenticated
                ? 'Logout'
                : 'Login';

        if (stateText)
        {
            stateText.textContent =
                authAuthenticated
                    ? 'Unlocked for this browser'
                    : 'Locked · read-only';
        }
    }

    if (lockState)
    {
        lockState.title =
            (!authEnabled || authAuthenticated)
                ? 'Settings unlocked'
                : 'Settings locked';
    }

    if (lockShackle)
    {
        lockShackle.setAttribute(
            'd',
            (!authEnabled || authAuthenticated)
                ? 'M8 11v-5a4 4 0 0 1 7.8 -1.2'
                : 'M8 11v-4a4 4 0 1 1 8 0v4');
    }

    if (loginPassword)
    {
        loginPassword.disabled =
            !authEnabled || authAuthenticated;
    }
}

async function loadAuthStatus()
{
    try
    {
        const response =
            await authenticatedFetch(
                '/api/auth/status');

        const data =
            await response.json();

        authEnabled =
            data.enabled;
        authAuthenticated =
            data.authenticated;

        if (!authAuthenticated)
        {
            authToken = '';
            sessionStorage.removeItem(
                'uNodeAuthToken');
        }

        updateAuthButton();
        updateProtectedUi();
    }
    catch(error)
    {
        console.error(error);
    }
}

async function toggleAuth()
{
    if (!authEnabled)
    {
        showPage('system');
        alert(
            'No password is configured. Set one in the System tab if write protection is needed.');
        return;
    }

    if (authAuthenticated)
    {
        await authenticatedFetch(
            '/api/auth/logout',
            {
                method: 'POST'
            });

        authToken = '';
        sessionStorage.removeItem(
            'uNodeAuthToken');
        await loadAuthStatus();
        return;
    }

    const passwordInput =
        document.getElementById(
            'loginPassword');

    const password =
        passwordInput
            ? passwordInput.value
            : prompt('Admin password');

    if (password === null)
    {
        return;
    }

    const response =
        await fetch(
            '/api/auth/login',
            {
                method: 'POST',
                headers:
                {
                    'Content-Type':
                        'application/json'
                },
                body:
                    JSON.stringify(
                    {
                        password
                    })
            });

    if (!response.ok)
    {
        alert(
            'Login failed: ' +
            await response.text());
        return;
    }

    if (passwordInput)
    {
        passwordInput.value = '';
    }

    const data =
        await response.json();

    authToken =
        data.token || '';

    if (authToken.length > 0)
    {
        sessionStorage.setItem(
            'uNodeAuthToken',
            authToken);
    }

    await loadAuthStatus();
}

async function loadStatus()
{
    try
    {
        const response =
            await fetch('/api/status');

        if (!response.ok)
        {
            throw new Error(
                'Status request failed: HTTP ' + response.status);
        }

        const data =
            await response.json();

        markConnectionOnline();

        document.getElementById('statusName').textContent =
            data.name;

        document.getElementById('statusIP').textContent =
            data.ip;

        document.getElementById('name').textContent =
            data.name;

		const direction =
			data.direction == 0
				? '\u2192'
				: '\u2190';

		document.getElementById(
			'dmxMode')
			.textContent =
				'Art-Net U'
				+ data.universe
				+ ' '
				+ direction
				+ ' DMX';

        setTextIfPresent(
            'sacnUniverseHint',
            'sACN Universe: '
            + (data.sacnUniverse ?? 'N/A')
            + ', derived from Art-Net Port-Address.');

        document.getElementById('firmware').textContent =
            data.firmware +
            " (" +
            data.buildDate +
            " " +
            data.buildTime +
            ")";

        const webAssetWarning =
            document.getElementById(
                'webAssetWarning');

        if (webAssetWarning)
        {
            const assetVersion =
                data.webAssetVersionPresent
                    ? data.webAssetVersion
                    : 'missing';
            const expectedVersion =
                data.webAssetExpectedVersion || data.firmware;

            webAssetWarning.hidden =
                data.webAssetVersionMatch !== false;

            webAssetWarning.textContent =
                'Web interface files do not match this firmware. '
                + 'Firmware expects '
                + expectedVersion
                + ', LittleFS has '
                + assetVersion
                + '. Upload the matching LittleFS image.';
        }

        document.getElementById('hostname').textContent =
            data.hostname;

        document.getElementById('ip').textContent =
            data.ip;

		document.getElementById('mac').textContent =
			data.mac;

		document.getElementById('chipId').textContent =
			'' + data.chipId;

		setTextIfPresent(
            'wifiInfo',
            data.wifiQuality +
            ' % (' +
            data.rssi +
            ' dBm)');

        document.getElementById('statusRSSI').textContent =
            data.wifiQuality + '%';

        if (data.dmxTestOverride !== undefined)
        {
            updateDmxOverrideStatus(
                data.dmxTestOverride,
                data.dmxTestOverrideRemaining || 0,
                data.dmxTestOverrideTimeoutEnabled !== false);
        }

		document.getElementById(
			'ledBrightnessSettings')
			.style.display =
				data.ledBrightnessSupported
					? 'block'
					: 'none';

        updateHardwareStatus(data);
        updateDetailedDiagnostics(data);
        updateStatusMessages(data);

        setTextIfPresent(
            'uptime',
            formatUptime(data.uptime));

        setTextIfPresent(
            'flashTotal',
            formatKB(data.flashSize));

        setTextIfPresent(
            'flashSketch',
            formatKB(data.sketchSize));

        setTextIfPresent(
            'flashFree',
            formatKB(data.freeSketch));

        setTextIfPresent(
            'fsUsed',
            formatKB(data.fsUsed));

        setTextIfPresent(
            'fsFree',
            formatKB(data.fsTotal - data.fsUsed));

        setTextIfPresent('freeHeap', formatKB(data.freeHeap || 0));
        setTextIfPresent('minimumFreeHeap', formatKB(data.minimumFreeHeap || 0));
        setTextIfPresent('maxFreeBlock', formatKB(data.maxFreeBlock || 0));
        setTextIfPresent(
            'heapFragmentation',
            (data.heapFragmentation ?? 0) + ' %');
        setTextIfPresent(
            'softAPStatus',
            (data.softAPActive ? 'active' : 'inactive')
                + ', stations '
                + (data.softAPStations ?? 0)
                + ', IP '
                + (data.softAPIP || '---'));
        setTextIfPresent(
            'storedWifiCredentials',
            data.storedWifiConfigured
                ? 'Stored Wi-Fi: ' + (data.storedWifiSSID || '(unnamed)')
                : 'Stored Wi-Fi: none');
        setTextIfPresent('resetReason', data.resetReason || '---');
        setTextIfPresent('resetInfo', data.resetInfo || '---');
        setTextIfPresent('bootCount', data.bootCount ?? '---');
        setTextIfPresent(
            'configSchemaVersion',
            data.configSchemaVersion ?? '---');
        setTextIfPresent(
            'webAssetVersionInfo',
            (data.webAssetVersionPresent ? data.webAssetVersion : 'missing')
                + ' / expected '
                + (data.webAssetExpectedVersion || data.firmware));

        updateDashboardRuntime(data);
		
    }
    catch(error)
    {
        console.error(error);
    }
}

function formatKB(bytes)
{
    return Math.round(bytes / 1024) + " kB";
}

function setTextIfPresent(id, value)
{
    const element = document.getElementById(id);

    if (element)
    {
        element.textContent =
            value === undefined
            || value === null
            || value === ''
                ? 'N/A'
                : value;
    }
}

function setFlowNodeState(id, state)
{
    const element =
        document.getElementById(id);

    if (!element)
    {
        return;
    }

    element.classList.remove(
        'idle',
        'ok',
        'warn',
        'error');
    element.classList.add(state);
}

function formatAge(ageMs)
{
    if (ageMs === undefined
        || ageMs === null
        || ageMs === 0)
    {
        return 'never';
    }

    if (ageMs < 1000)
    {
        return ageMs + ' ms ago';
    }

    return (ageMs / 1000).toFixed(1) + ' s ago';
}

function getArtSyncStateText(data)
{
    return data.artSyncActive
        ? (data.artSyncPending ? 'sync pending' : 'sync active')
        : 'async';
}

function updateDashboardModeLabels(data)
{
    const artnetToDmx =
        data.direction == 0;
    const liveProtocolName =
        data.liveProtocol == 1
            ? 'sACN'
            : 'Art-Net';

    setTextIfPresent(
        'artnetCardTitle',
        artnetToDmx ? liveProtocolName + ' Input' : liveProtocolName + ' Output');
    setTextIfPresent(
        'artnetSubscribersLabel',
        artnetToDmx ? 'Subscribers' : 'Art-Net Subscribers');
    setTextIfPresent(
        'dmxCardTitle',
        artnetToDmx ? 'DMX Output' : 'DMX Input');
    setTextIfPresent(
        'dmxStatusLabel',
        artnetToDmx ? 'Source' : 'Input Status');
}

function updateDashboardRuntime(data)
{
    const artnetToDmx =
        data.direction == 0;
    const usesSacn =
        data.liveProtocol == 1;
    const liveProtocolName =
        usesSacn ? 'sACN' : 'Art-Net';
    const liveInputActive =
        usesSacn ? data.sacnActive : data.artnetActive;
    const livePacketCount =
        usesSacn ? data.sacnPackets : data.artnetPackets;
    const liveFps =
        usesSacn ? data.sacnFPS : data.artnetFPS;
    const livePacketAge =
        usesSacn ? data.lastSacnPacketAge : data.lastPacketAge;

    updateDashboardModeLabels(data);

    const flowArtNetToDmx =
        document.getElementById('flowArtNetToDmx');
    const flowDmxToArtNet =
        document.getElementById('flowDmxToArtNet');

    if (flowArtNetToDmx)
    {
        flowArtNetToDmx.hidden =
            !artnetToDmx;
    }

    if (flowDmxToArtNet)
    {
        flowDmxToArtNet.hidden =
            artnetToDmx;
    }

    if (data.universe !== undefined
        && data.universe !== null)
    {
        lastKnownUniverse =
            data.universe;
    }

    const universeText =
        lastKnownUniverse === null
            ? 'N/A'
            : 'U' + lastKnownUniverse;
    const artNetSources =
        Array.isArray(data.artNetSources)
            ? data.artNetSources
            : [];
    const winningSource =
        artNetSources.find(source => source.winning)
        || artNetSources[0];

    setTextIfPresent(
        'flowNodeMeta',
        'Art-Net input · ' + universeText);
    setTextIfPresent(
        'flowNodeOutputMeta',
        'DMX input · ' + universeText);

    setTextIfPresent(
        'flowArtNetSource',
        winningSource
            ? (winningSource.name || winningSource.ip || 'Art-Net Controller')
            : 'N/A');
    setTextIfPresent(
        'flowArtNetSourceMeta',
        winningSource
            ? ((winningSource.ip || 'unknown IP')
                + ' · '
                + getArtSyncStateText(data)
                + ' · last '
                + formatAge(winningSource.lastSeenAge))
            : 'No active ArtDmx source');
    setTextIfPresent(
        'flowDmxOutMeta',
        data.failsafeActive
            ? 'Failsafe active · ' + data.failsafeModeName
            : (data.dmxTestOverride
                ? 'Web test override active'
                : (data.artnetActive
                    ? 'Sending physical DMX'
                    : 'Idle')));
    setTextIfPresent(
        'flowDmxInMeta',
        data.dmxFrames === undefined
            ? 'N/A'
            : ((data.dmxFrames ?? 0)
                + ' frames · '
                + (data.dmxFPS ?? 0)
                + ' fps · last '
                + formatAge(data.lastDMXFrameAge)));
    setTextIfPresent(
        'flowSubscriberMeta',
        data.artnetSubscribers === undefined
            ? 'N/A'
            : ((data.artnetSubscribers ?? 0)
                + ' subscribers · '
                + (data.dmxActive ? 'sending ArtDmx' : 'idle')));

    setFlowNodeState(
        'flowArtNetSourceNode',
        winningSource ? 'ok' : 'idle');
    setFlowNodeState(
        'flowNodeBox',
        data.wifiConnected === false ? 'warn' : 'ok');
    setFlowNodeState(
        'flowDmxOutNode',
        data.failsafeActive ? 'warn' : (data.artnetActive || data.dmxTestOverride ? 'ok' : 'idle'));
    setFlowNodeState(
        'flowDmxInNode',
        data.dmxActive ? 'ok' : 'idle');
    setFlowNodeState(
        'flowNodeOutputBox',
        data.wifiConnected === false ? 'warn' : 'ok');
    setFlowNodeState(
        'flowSubscriberNode',
        (data.artnetSubscribers ?? 0) > 0 ? 'ok' : 'idle');

    setTextIfPresent(
        'artSyncSummary',
        (data.artSyncs ?? 0)
            + ' packets (last '
            + formatAge(data.lastSyncAge)
            + ', '
            + getArtSyncStateText(data)
            + ')');
    setTextIfPresent(
        'artPollSummary',
        (data.artPolls ?? 0)
            + ' polls (last '
            + formatAge(data.lastPollAge)
            + ')');
    setTextIfPresent(
        'artnetSubscribers',
        data.artnetSubscribers ?? 0);
    setTextIfPresent(
        'failsafeStatus',
        artnetToDmx
            ? (data.failsafeActive
                ? 'Active: ' + data.failsafeModeName
                : 'Armed: ' + data.failsafeModeName)
            : 'Not used in DMX input mode');

    if (artnetToDmx)
    {
        setTextIfPresent(
            'artnetSummary',
            (data.artnetPackets ?? 0)
                + ' packets, '
                + (data.artnetFPS ?? 0)
                + ' fps (last '
                + formatAge(data.lastPacketAge)
                + ')');
        setTextIfPresent(
            'dmxSummary',
            (data.failsafeActive
                ? 'Failsafe active'
                : (data.dmxTestOverride
                    ? 'Test override'
                    : (data.artnetActive ? 'Sending DMX' : 'Idle')))
            + ' · Failsafe '
            + (data.failsafeActive ? 'active' : 'armed')
            + ': '
            + (data.failsafeModeName || 'N/A'));
        setTextIfPresent(
            'dmxStatus',
            data.dmxTestOverride
                ? 'DMX Test'
                : (data.artnetActive ? 'Art-Net' : 'None'));
    }
    else
    {
        setTextIfPresent(
            'artnetSummary',
            data.dmxActive ? 'Sending ArtDmx' : 'Idle');
        setTextIfPresent(
            'dmxSummary',
            (data.dmxFrames ?? 0)
                + ' frames, '
                + (data.dmxFPS ?? 0)
                + ' fps (last '
                + formatAge(data.lastDMXFrameAge)
                + ') · Failsafe not used');
        setTextIfPresent(
            'dmxStatus',
            data.dmxActive
                ? 'Receiving physical DMX'
                : 'No recent DMX');
    }

    if (usesSacn)
    {
        setTextIfPresent(
            'flowNodeMeta',
            'sACN input - ' + universeText);
        setTextIfPresent(
            'flowArtNetSource',
            'sACN Source');
        setTextIfPresent(
            'flowArtNetSourceMeta',
            (data.sacnActive ? 'Active' : 'Idle')
                + ' - last '
                + formatAge(data.lastSacnPacketAge));
        setTextIfPresent(
            'artnetSummary',
            (livePacketCount ?? 0)
                + ' packets, '
                + (liveFps ?? 0)
                + ' fps (last '
                + formatAge(livePacketAge)
                + ')');

        if (artnetToDmx)
        {
            setTextIfPresent(
                'flowDmxOutMeta',
                data.failsafeActive
                    ? 'Failsafe active - ' + data.failsafeModeName
                    : (data.dmxTestOverride
                        ? 'Web test override active'
                        : (liveInputActive ? 'Sending physical DMX' : 'Idle')));
            setTextIfPresent(
                'dmxSummary',
                (data.failsafeActive
                    ? 'Failsafe active'
                    : (data.dmxTestOverride
                        ? 'Test override'
                        : (liveInputActive ? 'Sending DMX' : 'Idle')))
                + ' - Failsafe '
                + (data.failsafeActive ? 'active' : 'armed')
                + ': '
                + (data.failsafeModeName || 'N/A'));
            setTextIfPresent(
                'dmxStatus',
                data.dmxTestOverride
                    ? 'DMX Test'
                    : (liveInputActive ? liveProtocolName : 'None'));
        }
        else
        {
            setTextIfPresent(
                'artnetSummary',
                data.dmxActive ? 'Sending sACN' : 'Idle');
        }

        setFlowNodeState(
            'flowArtNetSourceNode',
            data.sacnActive ? 'ok' : 'idle');
        setFlowNodeState(
            'flowDmxOutNode',
            data.failsafeActive ? 'warn' : (liveInputActive || data.dmxTestOverride ? 'ok' : 'idle'));
    }
}

function formatUptime(ms)
{
    let sec = Math.floor(ms / 1000);

    let days = Math.floor(sec / 86400);
    sec %= 86400;

    let hours = Math.floor(sec / 3600);
    sec %= 3600;

    let mins = Math.floor(sec / 60);

    return `${days}d ${hours}h ${mins}m`;
}

async function loadConfig()
{
    try
    {
        const response =
            await fetch('/api/config');

        const cfg =
            await response.json();

        document.getElementById(
            'shortName'
        ).value =
            cfg.shortName;

        document.getElementById(
            'longName'
        ).value =
            cfg.longName;

        document.getElementById(
            'net'
        ).value =
            cfg.net;

        document.getElementById(
            'subnetId'
        ).value =
            cfg.subnetId;

        document.getElementById(
            'universe'
        ).value =
            cfg.universe;

        document.getElementById(
            'failsafeMode'
        ).value =
            cfg.failsafeMode ?? 0;

        document.getElementById(
            'mergeMode'
        ).value =
            cfg.mergeMode ?? 0;

        document.getElementById(
            'liveProtocol'
        ).value =
            cfg.liveProtocol ?? 0;

        document.getElementById(
            'sacnSourceName'
        ).value =
            cfg.sacnSourceName ?? cfg.longName ?? 'uNode';

        document.getElementById(
            'sacnPriority'
        ).value =
            cfg.sacnPriority ?? 100;

        document.getElementById(
            'legacyArtPollReply'
        ).checked =
            cfg.legacyArtPollReply ?? false;

        document.getElementById(
            'terminationMode'
        ).value =
            cfg.terminationMode ?? 2;

        document.getElementById(
            'busGuardMode'
        ).value =
            cfg.busGuardMode ?? 0;

		if (cfg.direction == 0)
		{
			document.getElementById(
				'artnetToDmx'
			).checked = true;
		}
		else
		{
			document.getElementById(
				'dmxToArtnet'
			).checked = true;
		}

		updateDirectionMode();

        document.getElementById(
            'hostnameInput'
        ).value =
            cfg.hostname;

        document.getElementById(
            'wifiMode'
        ).value =
            cfg.wifiMode;

        document.getElementById(
            'ipAddress'
        ).value =
            cfg.ip;

        document.getElementById(
            'subnetMask'
        ).value =
            cfg.subnet;

        document.getElementById(
            'gateway'
        ).value =
            cfg.gateway;

		await refreshArtNetSubscribers();
	
	
		if (cfg.dhcp)
		{
			document.getElementById(
				'dhcp'
			).checked = true;
		}
		else
		{
			document.getElementById(
				'staticIp'
			).checked = true;
		}
		
		updateIPMode();
		
		document.getElementById(
			'ledBrightness'
		).value =
			cfg.ledBrightness;

		document.getElementById(
			'ledBrightnessValue'
		).textContent =
			cfg.ledBrightness + " %";

        configBaseline =
            readConfigForm();

        initializeConfigWatch();
        updateUnsavedChangesIndicator();
        await applyBrightnessPreview(
            cfg.ledBrightness,
            false);

    }
    catch(error)
    {
        console.error(error);
    }
}

function setIndicator(id, color)
{
    document.getElementById(
        id
    ).style.color =
        color;
}

function updateHardwareStatus(data)
{
    lastHardwareStatus = data;

    if (data.rs485SplitControlSupported !== undefined)
    {
        const busGuardSelect =
            document.getElementById(
                'busGuardMode');

        if (busGuardSelect)
        {
            busGuardSelect.disabled =
                isUiLocked();
        }

        setTextIfPresent(
            'rs485GuardStatus',
            (data.busGuardMode ?? 0) == 1
                ? 'Listens briefly at boot and switches to DMX input when external DMX is detected.'
                : 'Disabled. The configured direction is used at boot.');
    }

    if (data.terminationControlSupported !== undefined)
    {
        const terminationSelect =
            document.getElementById(
                'terminationMode');

        if (terminationSelect)
        {
            terminationSelect.disabled =
                isUiLocked()
                || !data.terminationControlSupported;
        }

        setTextIfPresent(
            'terminationStatus',
            data.terminationControlSupported
                ? (data.terminationEnabled ? 'On' : 'Off')
                : 'Not available in this build');
    }

    if (data.rs485DriverEnabled !== undefined)
    {
        setTextIfPresent(
            'rs485DriverStatus',
            data.rs485DriverEnabled
                ? 'Enabled'
                : 'Disabled');
    }

    if (data.rs485ReceiverEnabled !== undefined)
    {
        setTextIfPresent(
            'rs485ReceiverStatus',
            data.rs485ReceiverEnabled
                ? 'Enabled'
                : 'Disabled');
    }
}

function updateDetailedDiagnostics(data)
{
    const diagnostics =
        data.artNetDiagnostics;

    if (!diagnostics)
    {
        return;
    }

    setTextIfPresent(
        'diagArtOversizedPackets',
        diagnostics.oversizedPackets ?? 0);
    setTextIfPresent(
        'diagArtShortPackets',
        diagnostics.shortPackets ?? 0);
    setTextIfPresent(
        'diagArtInvalidIdPackets',
        diagnostics.invalidIdPackets ?? 0);
    setTextIfPresent(
        'diagArtUnsupportedProtocolPackets',
        diagnostics.unsupportedProtocolPackets ?? 0);
    setTextIfPresent(
        'diagArtMalformedPackets',
        diagnostics.malformedPackets ?? 0);
    setTextIfPresent(
        'diagArtUnsupportedOpcodes',
        diagnostics.unsupportedOpcodes ?? 0);
    setTextIfPresent(
        'diagArtWrongUniversePackets',
        diagnostics.wrongUniversePackets ?? 0);
    setTextIfPresent(
        'diagArtLastWrongUniverse',
        diagnostics.wrongUniversePackets > 0
            ? ('U' + (diagnostics.lastWrongUniverse ?? '?'))
            : '---');
    setTextIfPresent(
        'diagArtLastWrongUniverseAge',
        diagnostics.wrongUniversePackets > 0
            ? ((diagnostics.lastWrongUniverseAge ?? 0) + ' ms')
            : '---');
    setTextIfPresent(
        'diagArtProtocolDrops',
        diagnostics.protocolDrops ?? 0);
    setTextIfPresent(
        'diagArtDirectionDrops',
        diagnostics.directionDrops ?? 0);
    setTextIfPresent(
        'diagArtSequenceDrops',
        diagnostics.sequenceDrops ?? 0);
    setTextIfPresent(
        'diagArtMergeLockDrops',
        diagnostics.mergeLockDrops ?? 0);
    setTextIfPresent(
        'diagArtMergeThirdSourceDrops',
        diagnostics.mergeThirdSourceDrops ?? 0);
    setTextIfPresent(
        'diagArtSyncTimeouts',
        diagnostics.syncTimeouts ?? 0);

    const sacnDiagnostics =
        data.sacnDiagnostics;

    setTextIfPresent(
        'diagSacnUdpPackets',
        data.sacnUdpPackets ?? 0);
    setTextIfPresent(
        'diagSacnPackets',
        data.sacnPackets ?? 0);

    if (!sacnDiagnostics)
    {
        return;
    }

    setTextIfPresent(
        'diagSacnMalformedPackets',
        sacnDiagnostics.malformedPackets ?? 0);
    setTextIfPresent(
        'diagSacnWrongUniversePackets',
        sacnDiagnostics.wrongUniversePackets ?? 0);
    setTextIfPresent(
        'diagSacnLastWrongUniverse',
        (sacnDiagnostics.wrongUniversePackets ?? 0) > 0
            ? ('U' + (sacnDiagnostics.lastWrongUniverse ?? '?'))
            : '---');
    setTextIfPresent(
        'diagSacnProtocolDrops',
        sacnDiagnostics.protocolDrops ?? 0);
    setTextIfPresent(
        'diagSacnDirectionDrops',
        sacnDiagnostics.directionDrops ?? 0);
    setTextIfPresent(
        'diagSacnSequenceDrops',
        sacnDiagnostics.sequenceDrops ?? 0);
    setTextIfPresent(
        'diagSacnPriorityDrops',
        sacnDiagnostics.priorityDrops ?? 0);
    setTextIfPresent(
        'diagSacnStreamTerminated',
        sacnDiagnostics.streamTerminated ?? 0);
    setTextIfPresent(
        'diagSacnActiveSources',
        sacnDiagnostics.activeSources ?? 0);
    setTextIfPresent(
        'diagSacnWinningPriority',
        sacnDiagnostics.winningPriority ?? 0);
    setTextIfPresent(
        'diagSacnSourceTimeouts',
        sacnDiagnostics.sourceTimeouts ?? 0);
}

function updateStatusMessages(data)
{
    const warning =
        document.getElementById(
            'statusWarning');
    const warningText =
        document.getElementById(
            'statusWarningText');

    if (!warning || !warningText)
    {
        return;
    }

    const diagnostics =
        data.artNetDiagnostics;
    const sacnDiagnostics =
        data.sacnDiagnostics;
    const messages = [];
    const artNetProtocolDrops =
        Number(
            diagnostics?.protocolDrops ?? 0);
    const sacnProtocolDrops =
        Number(
            sacnDiagnostics?.protocolDrops ?? 0);

    if (lastArtNetProtocolDrops === null)
    {
        lastArtNetProtocolDrops =
            artNetProtocolDrops;
    }

    if (lastSacnProtocolDrops === null)
    {
        lastSacnProtocolDrops =
            sacnProtocolDrops;
    }

    if (data.direction == 0
        && diagnostics
        && diagnostics.wrongUniverseWarningActive)
    {
        wrongUniverseWarningVisibleUntil =
            Date.now() + wrongUniverseWarningHoldMs;
        lastWrongUniverseWarning =
            diagnostics.lastWrongUniverse ?? '?';
    }

    if (Date.now() < wrongUniverseWarningVisibleUntil)
    {
        messages.push(
            'Recent ArtDmx on wrong universe U'
            + lastWrongUniverseWarning
            + ' - check controller/node universe');
    }

    if (data.liveProtocol == 1
        && diagnostics
        && artNetProtocolDrops > lastArtNetProtocolDrops)
    {
        protocolMismatchWarningVisibleUntil =
            Date.now() + wrongUniverseWarningHoldMs;
        lastProtocolMismatchWarning =
            'Received ArtDmx while sACN is selected';
    }

    if (data.liveProtocol == 0
        && sacnDiagnostics
        && sacnProtocolDrops > lastSacnProtocolDrops)
    {
        protocolMismatchWarningVisibleUntil =
            Date.now() + wrongUniverseWarningHoldMs;
        lastProtocolMismatchWarning =
            'Received sACN while Art-Net is selected';
    }

    if (Date.now() < protocolMismatchWarningVisibleUntil)
    {
        messages.push(
            'Protocol mismatch: '
            + lastProtocolMismatchWarning
            + ' - check settings');
    }

    if (data.webAssetVersionMatch === false)
    {
        messages.push(
            'Firmware/Web files mismatch');
    }

    if (data.heapWarningActive)
    {
        messages.push(
            'Heap headroom low - check diagnostics');
    }

    if (data.direction == 0
        && data.failsafeActive)
    {
        messages.push(
            'Output failsafe active: '
            + (data.failsafeModeName || 'configured mode'));
    }

    lastArtNetProtocolDrops =
        artNetProtocolDrops;
    lastSacnProtocolDrops =
        sacnProtocolDrops;

    if (data.dmxTestOverride)
    {
        messages.push(
            'DMX test override active'
            + (data.dmxTestOverrideTimeoutEnabled === false
                ? ' (timeout disabled)'
                : (data.dmxTestOverrideRemaining
                ? ' ('
                    + Math.ceil(data.dmxTestOverrideRemaining / 1000)
                    + 's)'
                : '')));
    }

    if (messages.length > 0)
    {
        warning.hidden = false;
        warningText.textContent =
            messages.join(' · ');
        return;
    }

    warning.hidden = true;
}

const restartPollInterval = 1000;
const restartTimeout = 120000;
const statusPollInterval = 5000;
const connectionRetryInterval = 1000;
const wrongUniverseWarningHoldMs = 8000;
let restartInProgress = false;
let connectionOnline = true;
let connectionRecoveryInProgress = false;
let connectionLostSince = 0;
let configBaseline = null;
let configWatchInitialized = false;
let lastHardwareStatus = null;
let wrongUniverseWarningVisibleUntil = 0;
let lastWrongUniverseWarning = '?';
let protocolMismatchWarningVisibleUntil = 0;
let lastProtocolMismatchWarning = '';
let lastArtNetProtocolDrops = null;
let lastSacnProtocolDrops = null;

const restartRequiredConfigKeys =
[
    'hostname',
    'wifiMode',
    'dhcp',
    'ip',
    'subnet',
    'gateway',
    'busGuardMode'
];

const configFieldIds =
[
    'hostnameInput',
    'wifiMode',
    'dhcp',
    'staticIp',
    'ipAddress',
    'subnetMask',
    'gateway',
    'ledBrightness',
    'shortName',
    'longName',
    'artnetToDmx',
    'dmxToArtnet',
    'net',
    'subnetId',
    'universe',
    'failsafeMode',
    'mergeMode',
    'liveProtocol',
    'sacnSourceName',
    'sacnPriority',
    'terminationMode',
    'busGuardMode',
    'legacyArtPollReply'
];

function sleep(milliseconds)
{
    return new Promise(resolve =>
        setTimeout(resolve, milliseconds));
}

function showConnectionOverlay(title, message)
{
    document.getElementById(
        'connectionOverlayTitle')
        .textContent = title;

    document.getElementById(
        'restartStatus')
        .textContent = message;

    document.getElementById(
        'restartOverlay')
        .hidden = false;
}

function showRestartOverlay(message)
{
    showConnectionOverlay(
        'Node is restarting',
        message);
}

function hideRestartOverlay()
{
    document.getElementById(
        'restartOverlay')
        .hidden = true;
}

function markConnectionOnline()
{
    connectionOnline = true;

    if (!restartInProgress && !connectionRecoveryInProgress)
    {
        hideRestartOverlay();
    }
}

async function checkNodeOnline()
{
    const controller =
        new AbortController();

    const requestTimeout =
        setTimeout(
            () => controller.abort(),
            connectionRetryInterval);

    try
    {
        const response =
            await fetch(
                '/api/status?connectionCheck=' + Date.now(),
                {
                    cache: 'no-store',
                    signal: controller.signal
                });

        return response.ok;
    }
    catch(error)
    {
        return false;
    }
    finally
    {
        clearTimeout(requestTimeout);
    }
}

async function beginConnectionRecovery()
{
    if (restartInProgress || connectionRecoveryInProgress)
    {
        return;
    }

    connectionOnline = false;
    connectionRecoveryInProgress = true;
    connectionLostSince = Date.now();

    while (connectionRecoveryInProgress && !restartInProgress)
    {
        const offlineSeconds =
            Math.floor(
                (Date.now() - connectionLostSince) / 1000);

        showConnectionOverlay(
            'Connection lost',
            'Node is unavailable. Reconnecting... '
                + offlineSeconds
                + ' s');

        if (await checkNodeOnline())
        {
            showConnectionOverlay(
                'Connection restored',
                'Node is online again. Refreshing status...');

            connectionOnline = true;
            connectionRecoveryInProgress = false;

            await sleep(300);
            hideRestartOverlay();
            await loadAuthStatus();
            await loadConfig();
            await loadStatus();
            return;
        }

        await sleep(connectionRetryInterval);
    }
}

function readConfigForm()
{
    return {
        hostname:
            document.getElementById(
                'hostnameInput'
            ).value,

        wifiMode:
            parseInt(
                document.getElementById(
                    'wifiMode'
                ).value),

        dhcp:
            document.getElementById(
                'dhcp'
            ).checked,

        ip:
            document.getElementById(
                'ipAddress'
            ).value,

        subnet:
            document.getElementById(
                'subnetMask'
            ).value,

        gateway:
            document.getElementById(
                'gateway'
            ).value,

        ledBrightness:
            parseInt(
                document.getElementById(
                    'ledBrightness'
                ).value),

        shortName:
            document.getElementById(
                'shortName'
            ).value,

        longName:
            document.getElementById(
                'longName'
            ).value,

        direction:
            document.getElementById(
                'dmxToArtnet'
            ).checked
            ? 1
            : 0,

        net:
            parseInt(
                document.getElementById(
                    'net'
                ).value),

        subnetId:
            parseInt(
                document.getElementById(
                    'subnetId'
                ).value),

        universe:
            parseInt(
                document.getElementById(
                    'universe'
                ).value),

        failsafeMode:
            parseInt(
                document.getElementById(
                    'failsafeMode'
                ).value),

        mergeMode:
            parseInt(
                document.getElementById(
                    'mergeMode'
                ).value),

        liveProtocol:
            parseInt(
                document.getElementById(
                    'liveProtocol'
                ).value),

        sacnSourceName:
            document.getElementById(
                'sacnSourceName'
            ).value,

        sacnPriority:
            parseInt(
                document.getElementById(
                    'sacnPriority'
                ).value),

        terminationMode:
            parseInt(
                document.getElementById(
                    'terminationMode'
                ).value),

        busGuardMode:
            parseInt(
                document.getElementById(
                    'busGuardMode'
                ).value),

        legacyArtPollReply:
            document.getElementById(
                'legacyArtPollReply'
            ).checked
    };
}

function parseIPv4(value)
{
    const parts =
        value.trim().split('.');

    if (parts.length !== 4)
    {
        return null;
    }

    let result = 0;

    for (const part of parts)
    {
        if (!/^(0|[1-9][0-9]{0,2})$/.test(part))
        {
            return null;
        }

        const octet =
            Number(part);

        if (octet > 255)
        {
            return null;
        }

        result =
            ((result << 8) | octet) >>> 0;
    }

    return result >>> 0;
}

function isReservedHostAddress(value)
{
    const firstOctet =
        (value >>> 24) & 0xff;

    return firstOctet === 0
        || firstOctet === 127
        || firstOctet >= 224
        || value === 0xffffffff;
}

function isContiguousSubnetMask(mask)
{
    if (mask === 0
        || mask === 0xffffffff)
    {
        return false;
    }

    const inverted =
        (~mask) >>> 0;

    return (inverted & ((inverted + 1) >>> 0)) === 0;
}

function setStaticIpValidationError(message, fieldIds = [])
{
    [
        'ipAddress',
        'subnetMask',
        'gateway'
    ].forEach(id =>
    {
        document
            .getElementById(id)
            .classList
            .remove('invalid');
    });

    fieldIds.forEach(id =>
    {
        document
            .getElementById(id)
            .classList
            .add('invalid');
    });

    const messageElement =
        document.getElementById(
            'staticIpValidation');

    messageElement.textContent =
        message;
    messageElement.hidden =
        message.length === 0;
}

function validateStaticIpSettings(cfg)
{
    if (cfg.dhcp)
    {
        setStaticIpValidationError('');
        return true;
    }

    const ip =
        parseIPv4(cfg.ip);
    const subnet =
        parseIPv4(cfg.subnet);
    const gateway =
        parseIPv4(cfg.gateway);

    if (ip === null)
    {
        setStaticIpValidationError(
            'Static IP address is invalid.',
            ['ipAddress']);
        return false;
    }

    if (subnet === null)
    {
        setStaticIpValidationError(
            'Subnet mask is invalid.',
            ['subnetMask']);
        return false;
    }

    if (gateway === null)
    {
        setStaticIpValidationError(
            'Gateway address is invalid.',
            ['gateway']);
        return false;
    }

    if (isReservedHostAddress(ip))
    {
        setStaticIpValidationError(
            'Static IP address is reserved or multicast.',
            ['ipAddress']);
        return false;
    }

    if (isReservedHostAddress(gateway))
    {
        setStaticIpValidationError(
            'Gateway address is reserved or multicast.',
            ['gateway']);
        return false;
    }

    if (!isContiguousSubnetMask(subnet))
    {
        setStaticIpValidationError(
            'Subnet mask must be contiguous and usable.',
            ['subnetMask']);
        return false;
    }

    const network =
        (ip & subnet) >>> 0;
    const broadcast =
        (network | (~subnet >>> 0)) >>> 0;

    if (ip === network
        || ip === broadcast)
    {
        setStaticIpValidationError(
            'Static IP must not be the network or broadcast address.',
            ['ipAddress']);
        return false;
    }

    if (((gateway & subnet) >>> 0) !== network)
    {
        setStaticIpValidationError(
            'Gateway must be in the same subnet as the static IP.',
            ['gateway']);
        return false;
    }

    if (gateway === ip
        || gateway === network
        || gateway === broadcast)
    {
        setStaticIpValidationError(
            'Gateway must be a different usable host address.',
            ['gateway']);
        return false;
    }

    setStaticIpValidationError('');
    return true;
}

function countChangedConfigFields(
    current,
    baseline)
{
    if (!baseline)
    {
        return 0;
    }

    let changes = 0;

    Object.keys(current)
        .forEach(key =>
        {
            if (current[key] !== baseline[key])
            {
                changes++;
            }
        });

    return changes;
}

function hasRestartRequiredConfigChanges(
    current,
    baseline)
{
    if (!baseline)
    {
        return false;
    }

    return restartRequiredConfigKeys
        .some(key =>
            current[key] !== baseline[key]);
}

function updateUnsavedChangesIndicator()
{
    const indicator =
        document.getElementById(
            'unsavedChanges');

    const textLabel =
        document.getElementById(
            'unsavedChangesText');

    const saveButton =
        document.getElementById(
            'saveRestartButton');

    const current =
        readConfigForm();

    const count =
        countChangedConfigFields(
            current,
            configBaseline);

    if (count === 0)
    {
        indicator.hidden = true;
        return;
    }

    textLabel.textContent =
        count
        + ' unsaved change'
        + (count === 1 ? '' : 's');

    if (saveButton)
    {
        saveButton.textContent =
            hasRestartRequiredConfigChanges(
                current,
                configBaseline)
                ? 'Save & Restart'
                : 'Save';
    }

    indicator.hidden = false;
}

async function revertConfigChanges()
{
    if (!configBaseline)
    {
        await loadConfig();
        return;
    }

    document.getElementById('hostnameInput').value =
        configBaseline.hostname;
    document.getElementById('wifiMode').value =
        configBaseline.wifiMode;
    document.getElementById('ipAddress').value =
        configBaseline.ip;
    document.getElementById('subnetMask').value =
        configBaseline.subnet;
    document.getElementById('gateway').value =
        configBaseline.gateway;
    document.getElementById('ledBrightness').value =
        configBaseline.ledBrightness;
    document.getElementById('ledBrightnessValue').textContent =
        configBaseline.ledBrightness + ' %';
    document.getElementById('shortName').value =
        configBaseline.shortName;
    document.getElementById('longName').value =
        configBaseline.longName;
    document.getElementById('net').value =
        configBaseline.net;
    document.getElementById('subnetId').value =
        configBaseline.subnetId;
    document.getElementById('universe').value =
        configBaseline.universe;
    document.getElementById('failsafeMode').value =
        configBaseline.failsafeMode;
    document.getElementById('mergeMode').value =
        configBaseline.mergeMode;
    document.getElementById('liveProtocol').value =
        configBaseline.liveProtocol ?? 0;
    document.getElementById('sacnSourceName').value =
        configBaseline.sacnSourceName ?? configBaseline.longName ?? 'uNode';
    document.getElementById('sacnPriority').value =
        configBaseline.sacnPriority ?? 100;
    document.getElementById('terminationMode').value =
        configBaseline.terminationMode;
    document.getElementById('busGuardMode').value =
        configBaseline.busGuardMode;
    document.getElementById('legacyArtPollReply').checked =
        configBaseline.legacyArtPollReply;

    document.getElementById('dhcp').checked =
        configBaseline.dhcp;
    document.getElementById('staticIp').checked =
        !configBaseline.dhcp;
    document.getElementById('artnetToDmx').checked =
        configBaseline.direction == 0;
    document.getElementById('dmxToArtnet').checked =
        configBaseline.direction == 1;

    updateDirectionMode();
    updateIPMode();
    validateStaticIpSettings(configBaseline);
    updateUnsavedChangesIndicator();

    await applyBrightnessPreview(
        configBaseline.ledBrightness,
        false);
}

window.addEventListener(
    'beforeunload',
    event =>
    {
        if (restartInProgress
            || countChangedConfigFields(
                readConfigForm(),
                configBaseline) === 0)
        {
            return;
        }

        event.preventDefault();
        event.returnValue = '';
    });

function initializeConfigWatch()
{
    if (configWatchInitialized)
    {
        return;
    }

    configWatchInitialized = true;

    configFieldIds.forEach(id =>
    {
        const element =
            document.getElementById(id);

        if (!element)
        {
            return;
        }

        element.addEventListener(
            'input',
            updateUnsavedChangesIndicator);

        element.addEventListener(
            'change',
            updateUnsavedChangesIndicator);
    });

    [
        'ipAddress',
        'subnetMask',
        'gateway'
    ].forEach(id =>
    {
        const element =
            document.getElementById(id);

        if (!element)
        {
            return;
        }

        element.addEventListener(
            'input',
            () => validateStaticIpSettings(readConfigForm()));
    });
}

async function waitForRestartAndReload()
{
    showRestartOverlay(
        'Waiting for the node...');

    // Prevent the old HTTP server from answering the first health check
    // before the ESP has actually restarted.
    await sleep(1500);

    const deadline =
        Date.now() + restartTimeout;

    while (Date.now() < deadline)
    {
        const controller =
            new AbortController();

        const requestTimeout =
            setTimeout(
                () => controller.abort(),
                restartPollInterval);

        try
        {
            const response = await fetch(
                '/api/status?restartCheck=' + Date.now(),
                {
                    cache: 'no-store',
                    signal: controller.signal
                });

            if (response.ok)
            {
                showRestartOverlay(
                    'Node is online again. Reloading the page...');

                await sleep(300);
                window.location.reload();
                return;
            }
        }
        catch(error)
        {
            // Connection failures are expected while the ESP reboots.
        }
        finally
        {
            clearTimeout(requestTimeout);
        }

        await sleep(restartPollInterval);
    }

    restartInProgress = false;
    showRestartOverlay(
        'Node is still unavailable. Check the connection and IP address.');
}

async function restartAndReload()
{
    if (restartInProgress)
    {
        return;
    }

    restartInProgress = true;
    showRestartOverlay(
        'Requesting restart...');

    try
    {
        const response = await authenticatedFetch(
            '/api/restart',
            {
                method: 'POST'
            });

        if (!response.ok)
        {
            restartInProgress = false;
            hideRestartOverlay();
            alert(
                'Restart failed: ' +
                await response.text());
            return;
        }
    }
    catch(error)
    {
        // The reboot may close the socket before the response is complete.
        // Continue waiting for the node in that case.
    }

    await waitForRestartAndReload();
}

async function forgetWifiCredentials()
{
    if (restartInProgress)
    {
        return;
    }

    if (!confirm(
        'Forget the saved Wi-Fi SSID and password? '
            + 'The node will restart. uNode settings stay unchanged.'))
    {
        return;
    }

    restartInProgress = true;
    showRestartOverlay(
        'Clearing saved Wi-Fi credentials...');

    try
    {
        const response = await authenticatedFetch(
            '/api/wifi/forget',
            {
                method: 'POST'
            });

        if (!response.ok)
        {
            restartInProgress = false;
            hideRestartOverlay();
            alert(
                'Clearing Wi-Fi credentials failed: ' +
                await response.text());
            return;
        }
    }
    catch(error)
    {
        // The station interface may disappear before the response completes.
        // Continue waiting for the configured AP/recovery path.
    }

    await waitForRestartAndReload();
}

async function saveConfig()
{
    const cfg =
        readConfigForm();

    if (!validateStaticIpSettings(cfg))
    {
        showPage('network');
        return;
    }

    const response = await authenticatedFetch(
        '/api/config',
        {
            method: 'POST',

            headers:
            {
                'Content-Type':
                    'application/json'
            },

            body:
                JSON.stringify(cfg)
        });

    if (!response.ok)
    {
        alert(await response.text());
        return;
    }

    let result =
        {
            restartRequired: true
        };

    try
    {
        result =
            await response.json();
    }
    catch(error)
    {
        console.warn(
            'Config save response was not JSON; using restart fallback.',
            error);
    }

    if (result.restartRequired)
    {
        await restartAndReload();
        return;
    }

    configBaseline =
        readConfigForm();

    updateUnsavedChangesIndicator();
    await loadStatus();
}

async function detectNode()
{
    try
    {
        await authenticatedFetch(
            '/api/detect',
            {
                method: 'POST'
            });
    }
    catch(error)
    {
        console.error(error);
    }
}

async function applyBrightnessPreview(
    brightness,
    reportConnectionLoss = true)
{
    try
    {
        const response =
            await authenticatedFetch(
                '/api/brightness',
                {
                    method: 'POST',

                    headers:
                    {
                        'Content-Type':
                            'application/json'
                    },

                    body:
                        JSON.stringify(
                        {
                            brightness:
                                brightness
                        })
                });

        if (!response.ok)
        {
            throw new Error(
                'Brightness preview failed: HTTP ' + response.status);
        }
    }
    catch(error)
    {
        console.error(error);

        if (reportConnectionLoss)
        {
            beginConnectionRecovery();
        }
    }
}

async function updateBrightness()
{
    const brightness =
        parseInt(
            document.getElementById(
                'ledBrightness'
            ).value);

    document.getElementById(
        'ledBrightnessValue'
    ).textContent =
        brightness + " %";

    await applyBrightnessPreview(
        brightness);
}

async function downloadConfig()
{
    const response =
        await authenticatedFetch(
            '/api/config/download');

    if (!response.ok)
    {
        alert(
            'Download failed: ' +
            await response.text());
        return;
    }

    const blob =
        await response.blob();
    const url =
        URL.createObjectURL(blob);
    const link =
        document.createElement('a');

    link.href =
        url;
    link.download =
        'config.json';
    link.click();

    URL.revokeObjectURL(url);
}

async function uploadConfig()
{
    const file =
        document.getElementById(
            'configFile')
        .files[0];

    if (!file)
    {
        alert(
            'Select a configuration file first.');

        return;
    }

    const formData =
        new FormData();

    formData.append(
        'file',
        file);

    const response = await authenticatedFetch(
        '/api/config/upload?size=' + file.size,
        {
            method: 'POST',
            body: formData
        });

    if (!response.ok)
    {
        alert(
            'Upload failed: ' +
            await response.text());
        return;
    }

    await restartAndReload();
}

function formatEventLogLine(event)
{
    const repeatText =
        event.repeats > 0
            ? ' (repeated ' + event.repeats + 'x)'
            : '';

    return '['
        + formatUptime(event.uptime || 0)
        + '] '
        + (event.message || 'Unknown event')
        + repeatText;
}

async function refreshEventLog()
{
    const textArea =
        document.getElementById(
            'eventLogText');

    if (!textArea)
    {
        return;
    }

    try
    {
        const response =
            await fetch('/api/events');

        if (!response.ok)
        {
            throw new Error(
                await response.text());
        }

        const data =
            await response.json();
        const events =
            data.events || [];

        textArea.value =
            events.length > 0
                ? events
                    .map(formatEventLogLine)
                    .join('\n')
                : 'No events since last restart.';
    }
    catch(error)
    {
        textArea.value =
            'Failed to load event log: '
            + error;
    }
}

function downloadEventLog()
{
    window.location.href =
        '/api/events/download';
}

async function clearEventLog()
{
    const response =
        await authenticatedFetch(
            '/api/events/clear',
            {
                method: 'POST'
            });

    if (!response.ok)
    {
        alert(
            'Failed to clear event log: '
            + await response.text());
        return;
    }

    await refreshEventLog();
}

async function setAdminPassword()
{
    const input =
        document.getElementById(
            'adminPassword');

    const password =
        input.value;

    if (password.length === 0)
    {
        const confirmed =
            confirm(
                'Disable web write protection?');

        if (!confirmed)
        {
            return;
        }
    }

    const response =
        await authenticatedFetch(
            '/api/auth/password',
            {
                method: 'POST',
                headers:
                {
                    'Content-Type':
                        'application/json'
                },
                body:
                    JSON.stringify(
                    {
                        password
                    })
            });

    if (!response.ok)
    {
        alert(
            'Password update failed: ' +
            await response.text());
        return;
    }

    const data =
        await response.json();

    authToken =
        data.token || '';

    if (authToken.length > 0)
    {
        sessionStorage.setItem(
            'uNodeAuthToken',
            authToken);
    }
    else
    {
        sessionStorage.removeItem(
            'uNodeAuthToken');
    }

    input.value = '';
    await loadAuthStatus();

    alert(
        password.length > 0
            ? 'Password saved. The interface is unlocked for this browser until logout or reboot.'
            : 'Password disabled.');
}

async function recordFailsafeScene()
{
    const message =
        document.getElementById(
            'failsafeMessage');

    message.textContent =
        'Recording current output frame...';

    try
    {
        const response = await authenticatedFetch(
            '/api/failsafe/record',
            {
                method: 'POST'
            });

        if (!response.ok)
        {
            message.textContent =
                'Recording failed: ' +
                await response.text();
            return;
        }

        message.textContent =
            'Failsafe scene recorded.';
    }
    catch(error)
    {
        console.error(error);
        message.textContent =
            'Recording failed.';
    }
}

function uploadBinaryUpdate(
    inputId,
    endpoint,
    label)
{
    if (restartInProgress)
    {
        return;
    }

    const file =
        document.getElementById(
            inputId)
        .files[0];

    if (!file)
    {
        alert(
            'Select a file first.');
        return;
    }

    if (endpoint.endsWith('/fs'))
    {
        const confirmed =
            confirm(
                'This replaces the complete LittleFS filesystem, including the stored configuration. Download the configuration first if you want to keep it. Continue?');

        if (!confirmed)
        {
            return;
        }
    }

    restartInProgress = true;
    showRestartOverlay(
        label + ' upload is running...');

    const formData =
        new FormData();

    formData.append(
        'file',
        file);

    const request =
        new XMLHttpRequest();

    request.open(
        'POST',
        endpoint + '?size=' + file.size);

    if (authToken.length > 0)
    {
        request.setRequestHeader(
            'X-uNode-Auth',
            authToken);
    }

    request.onload =
        async () =>
    {
        if (request.status >= 200
            && request.status < 300)
        {
            showRestartOverlay(
                label + ' accepted. Waiting for restart...');

            await waitForRestartAndReload();
            return;
        }

        restartInProgress = false;
        hideRestartOverlay();
        alert(
            label + ' failed: ' +
            request.responseText);
    };

    request.onerror =
        () =>
    {
        restartInProgress = false;
        hideRestartOverlay();
        alert(
            label + ' failed: network error');
    };

    request.send(
        formData);
}

function uploadFirmware()
{
    uploadBinaryUpdate(
        'firmwareFile',
        '/api/update/firmware',
        'Firmware update');
}

function uploadFilesystem()
{
    uploadBinaryUpdate(
        'filesystemFile',
        '/api/update/fs',
        'LittleFS update');
}

function updateOtaButtons()
{
    const firmwareSelected =
        document.getElementById('firmwareFile')
        && document.getElementById('firmwareFile').files.length > 0;
    const filesystemSelected =
        document.getElementById('filesystemFile')
        && document.getElementById('filesystemFile').files.length > 0;
    const locked =
        isUiLocked();

    const firmwareButton =
        document.getElementById('updateFirmwareButton');
    const filesystemButton =
        document.getElementById('updateFilesystemButton');
    const bothButton =
        document.getElementById('updateBothButton');

    if (firmwareButton)
    {
        firmwareButton.disabled =
            locked || !firmwareSelected;
    }

    if (filesystemButton)
    {
        filesystemButton.disabled =
            locked || !filesystemSelected;
    }

    if (bothButton)
    {
        bothButton.disabled =
            locked || !firmwareSelected || !filesystemSelected;
    }
}

function uploadBoth()
{
    alert(
        'Combined firmware + LittleFS update needs firmware-side transaction support. Upload the two files separately for now.');
}

function createDMXMonitor()
{
    const monitor =
        document.getElementById(
            'dmxMonitor');

    monitor.innerHTML = '';

    for(let i=0;i<32;i++)
    {
        const div =
            document.createElement(
                'div');

        div.className =
            'dmxChannel';

        div.id =
            'dmx' + i;

        div.textContent =
            String(i + 1)
                .padStart(3,'0')
            + ': 0';

        monitor.appendChild(div);
    }
}

function updateIPMode()
{
    const useDhcp =
        document.getElementById(
            'dhcp'
        ).checked;

    document.getElementById(
        'staticSettings'
    ).style.display =
        'block';

    [
        'ipAddress',
        'subnetMask',
        'gateway'
    ].forEach(id =>
    {
        const element =
            document.getElementById(id);

        if (element)
        {
            element.disabled =
                useDhcp || isUiLocked();
        }
    });

    validateStaticIpSettings(
        readConfigForm());
}

function updateDirectionMode()
{
    const sendsArtNet =
        document.getElementById(
            'dmxToArtnet')
            .checked;
    const usesArtNet =
        parseInt(
            document.getElementById(
                'liveProtocol')
                .value) === 0;
    const usesSacn =
        !usesArtNet;

    document.getElementById(
        'artnetSubscriberSettings')
        .style.display =
            sendsArtNet && usesArtNet ? 'block' : 'none';

    document.getElementById(
        'sacnSettings')
        .style.display =
            usesSacn ? 'block' : 'none';

    document.getElementById(
        'failsafeSettings')
        .style.display =
            sendsArtNet ? 'none' : 'block';

    document.getElementById(
        'mergeSettings')
        .style.display =
            sendsArtNet || !usesArtNet ? 'none' : 'block';
}

function describeSubscriberPorts(subscriber)
{
    const ports = [];

    for(let port = 0; port < 4; port++)
    {
        if(subscriber.inputPortMask & (1 << port))
        {
            ports.push(`SwIn ${port + 1}`);
        }

        if(subscriber.outputPortMask & (1 << port))
        {
            ports.push(`SwOut ${port + 1}`);
        }
    }

    return ports.join(', ');
}

async function refreshArtNetSubscribers(
    waitForCompletion = false)
{
    try
    {
        const response =
            await fetch('/api/artnet/subscribers');

        if (!response.ok)
        {
            throw new Error(
                await response.text());
        }

        const data =
            await response.json();

        document.getElementById(
            'subscriberUniverse')
            .textContent = data.universe;

        const list =
            document.getElementById(
                'artnetSubscriberList');

        list.innerHTML = '';

        data.subscribers.forEach(subscriber =>
        {
            const label = document.createElement('div');
            label.className = 'label';
            label.textContent =
                subscriber.name || 'Art-Net Subscriber';

            const value = document.createElement('div');
            const bind = subscriber.bindIndex > 1
                ? ` \u00b7 Bind ${subscriber.bindIndex}`
                : '';
            value.textContent =
                `${subscriber.ip}${bind} \u00b7 `
                + `${describeSubscriberPorts(subscriber)} \u00b7 `
                + `${subscriber.lastSeenAge} ms ago`;

            list.appendChild(label);
            list.appendChild(value);
        });

        const status =
            document.getElementById(
                'artnetSubscriberStatus');

        if (data.polling)
        {
            status.textContent =
                'ArtPoll in progress \u2026';
        }
        else if (data.subscribers.length === 0)
        {
            status.textContent =
                'No subscribers found for this Universe.';
        }
        else
        {
            const subscriberCount =
                data.subscribers.length;

            status.textContent =
                `${subscriberCount} subscriber`
                + `${subscriberCount === 1 ? '' : 's'} active.`;
        }

        if (waitForCompletion && data.polling)
        {
            setTimeout(
                () => refreshArtNetSubscribers(true),
                400);
        }
    }
    catch(error)
    {
        console.error(error);

        document.getElementById(
            'artnetSubscriberStatus')
            .textContent =
                'Subscriber query failed.';
    }
}

async function pollArtNetSubscribers()
{
    const status =
        document.getElementById(
            'artnetSubscriberStatus');

    status.textContent =
        'Sending ArtPoll \u2026';

    try
    {
        const response = await authenticatedFetch(
            '/api/artnet/poll',
            {
                method: 'POST'
            });

        if (!response.ok)
        {
            throw new Error(
                await response.text());
        }

        await refreshArtNetSubscribers(true);
    }
    catch(error)
    {
        console.error(error);
        status.textContent =
            'Subscriber query failed.';
    }
}

const dmxTestFaderCount = 4;
let dmxMonitorSnapshot = [];
let dmxTestOverrideActive = false;
let dmxTestOverrideTimeoutEnabled = true;
let dmxPatternTimer = null;
let dmxPatternRunning = false;
let dmxPatternPaused = false;
let dmxPatternMode = 'chase';
let dmxPatternStart = 1;
let dmxPatternEnd = 16;
let dmxPatternCurrent = 1;

function getDmxTestStartAddress()
{
    const input =
        document.getElementById(
            'dmxStartAddress');

    let value =
        parseInt(input.value);

    if (Number.isNaN(value))
    {
        value = 1;
    }

    value =
        Math.min(
            Math.max(value, 1),
            512 - dmxTestFaderCount + 1);

    input.value =
        value;

    return value;
}

function clampDmxChannel(value)
{
    if (Number.isNaN(value))
    {
        return 1;
    }

    return Math.min(
        Math.max(value, 1),
        512);
}

function updateDmxTestFaderValue(
    faderIndex,
    value)
{
    const faderNumber =
        faderIndex + 1;

    document
        .getElementById('dmxCh' + faderNumber)
        .value =
            value;

    document
        .getElementById('dmxCh' + faderNumber + 'Value')
        .textContent =
            value;
}

function updateDmxTestLabels()
{
    const startAddress =
        getDmxTestStartAddress();

    for (let i = 0; i < dmxTestFaderCount; i++)
    {
        const channel =
            startAddress + i;

        document
            .getElementById('dmxCh' + (i + 1) + 'Label')
            .textContent =
                'Ch ' + String(channel).padStart(3, '0');
    }
}

function syncDmxTestFadersFromMonitor()
{
    if (dmxTestOverrideActive)
    {
        return;
    }

    const startAddress =
        getDmxTestStartAddress();

    for (let i = 0; i < dmxTestFaderCount; i++)
    {
        const channel =
            startAddress + i;

        if (channel <= dmxMonitorSnapshot.length)
        {
            updateDmxTestFaderValue(
                i,
                dmxMonitorSnapshot[channel - 1]);
        }
    }
}

function updateDmxOverrideStatus(
    active,
    remaining,
    timeoutEnabled = dmxTestOverrideTimeoutEnabled)
{
    dmxTestOverrideActive =
        active;
    dmxTestOverrideTimeoutEnabled =
        timeoutEnabled;

    const status =
        document.getElementById(
            'dmxOverrideStatus');

    if (!status)
    {
        return;
    }

    status.classList.toggle(
        'active',
        active);

    const releaseButton =
        document.getElementById(
            'releaseDmxOverrideButton');

    if (releaseButton)
    {
        releaseButton.disabled =
            isUiLocked() || !active;
    }

    const holdCheckbox =
        document.getElementById(
            'dmxOverrideHold');

    if (holdCheckbox)
    {
        holdCheckbox.checked =
            !timeoutEnabled;
        holdCheckbox.disabled =
            isUiLocked();
    }

    status.textContent =
        active
            ? (timeoutEnabled
                ? 'Override active - fallback in '
                    + Math.ceil(remaining / 1000)
                    + ' s'
                : 'Override active - timeout disabled')
            : 'Override idle';
}

async function sendDmxTestValues(
    startChannel,
    values)
{
    try
    {
        await authenticatedFetch(
            '/api/dmx',
            {
                method: 'POST',
                headers:
                {
                    'Content-Type':
                        'application/json'
                },
                body: JSON.stringify(
                {
                    startChannel,
                    values
                })
            });
    }
    catch(error)
    {
        console.error(error);
    }
}

async function sendFullDmxTestFrame(activeChannel = 0, activeValue = 255)
{
    const values =
        Array(512).fill(0);

    if (activeChannel >= 1
        && activeChannel <= 512)
    {
        values[activeChannel - 1] =
            activeValue;
    }

    await sendDmxTestValues(
        1,
        values);
}

async function setDmxChannel(
    channel,
    value)
{
    await sendDmxTestValues(
        channel,
        [value]);
}

async function setVisibleDmxTestValues(value)
{
    const values =
        Array(dmxTestFaderCount).fill(value);

    values.forEach((item, index) =>
    {
        updateDmxTestFaderValue(
            index,
            item);
    });

    await sendDmxTestValues(
        getDmxTestStartAddress(),
        values);
}

async function releaseDmxOverride()
{
    stopDmxPattern(false);

    try
    {
        await authenticatedFetch(
            '/api/dmx/release',
            {
                method: 'POST'
            });
    }
    catch(error)
    {
        console.error(error);

        beginConnectionRecovery();
    }
}

async function setDmxOverrideTimeoutEnabled(enabled)
{
    try
    {
        await authenticatedFetch(
            '/api/dmx/timeout',
            {
                method: 'POST',
                headers:
                {
                    'Content-Type':
                        'application/json'
                },
                body: JSON.stringify(
                {
                    enabled
                })
            });

        dmxTestOverrideTimeoutEnabled =
            enabled;

        updateDmxOverrideStatus(
            dmxTestOverrideActive,
            0,
            enabled);
    }
    catch(error)
    {
        console.error(error);
    }
}

function readDmxPatternRange()
{
    const startInput =
        document.getElementById(
            'dmxPatternStart');
    const endInput =
        document.getElementById(
            'dmxPatternEnd');

    let start =
        clampDmxChannel(
            parseInt(startInput.value));
    let end =
        clampDmxChannel(
            parseInt(endInput.value));

    if (end < start)
    {
        [start, end] = [end, start];
    }

    startInput.value =
        start;
    endInput.value =
        end;

    return { start, end };
}

function getDmxPatternSpeed()
{
    const value =
        parseInt(
            document.getElementById(
                'dmxPatternSpeed').value);

    return Number.isNaN(value)
        ? 500
        : value;
}

function updateDmxPatternControls()
{
    setTextIfPresent(
        'dmxPatternChannel',
        dmxPatternRunning
            ? String(dmxPatternCurrent).padStart(3, '0')
            : '---');

    const running =
        dmxPatternRunning;
    const locked =
        isUiLocked();

    const startButtons =
        [
            'channelChaseButton',
            'findAddressButton'
        ];
    const runningButtons =
        [
            'patternPauseButton',
            'patternPreviousButton',
            'patternNextButton',
            'patternStopButton'
        ];

    startButtons.forEach(id =>
    {
        const element =
            document.getElementById(id);

        if (element)
        {
            element.disabled =
                locked || running;
        }
    });

    runningButtons.forEach(id =>
    {
        const element =
            document.getElementById(id);

        if (element)
        {
            element.disabled =
                locked || !running;
        }
    });

    const pauseButton =
        document.getElementById(
            'patternPauseButton');

    if (pauseButton)
    {
        pauseButton.textContent =
            dmxPatternPaused
                ? 'Resume'
                : 'Pause';
    }
}

async function showDmxPatternChannel(channel)
{
    dmxPatternCurrent =
        channel;

    updateDmxPatternControls();

    await sendFullDmxTestFrame(
        channel,
        255);
}

function scheduleNextDmxPatternStep()
{
    clearTimeout(dmxPatternTimer);

    if (!dmxPatternRunning
        || dmxPatternPaused)
    {
        return;
    }

    dmxPatternTimer =
        setTimeout(
            () =>
            {
                stepDmxPattern(1);
            },
            getDmxPatternSpeed());
}

function startDmxPattern(mode)
{
    const range =
        readDmxPatternRange();

    dmxPatternMode =
        mode;
    dmxPatternStart =
        range.start;
    dmxPatternEnd =
        range.end;
    dmxPatternCurrent =
        dmxPatternStart;
    dmxPatternRunning =
        true;
    dmxPatternPaused =
        false;

    updateDmxPatternControls();
    showDmxPatternChannel(
        dmxPatternCurrent)
        .then(() =>
        {
            if (dmxPatternMode === 'find')
            {
                dmxPatternPaused =
                    true;
                updateDmxPatternControls();
                return;
            }

            scheduleNextDmxPatternStep();
        });
}

function startDmxChannelChase()
{
    startDmxPattern('chase');
}

function startDmxFindAddress()
{
    startDmxPattern('find');
}

function toggleDmxPatternPause()
{
    if (!dmxPatternRunning)
    {
        return;
    }

    dmxPatternPaused =
        !dmxPatternPaused;

    updateDmxPatternControls();
    scheduleNextDmxPatternStep();
}

function stepDmxPattern(direction)
{
    if (!dmxPatternRunning)
    {
        return;
    }

    clearTimeout(dmxPatternTimer);

    let next =
        dmxPatternCurrent + direction;

    if (dmxPatternMode === 'find'
        && next > dmxPatternEnd)
    {
        next =
            dmxPatternEnd;
        dmxPatternPaused =
            true;
    }
    else if (dmxPatternMode === 'find'
        && next < dmxPatternStart)
    {
        next =
            dmxPatternStart;
    }
    else if (next > dmxPatternEnd)
    {
        next =
            dmxPatternStart;
    }
    else if (next < dmxPatternStart)
    {
        next =
            dmxPatternEnd;
    }

    showDmxPatternChannel(next)
        .then(scheduleNextDmxPatternStep);
}

async function stopDmxPattern(clearOutput = true)
{
    clearTimeout(dmxPatternTimer);
    dmxPatternTimer =
        null;
    dmxPatternRunning =
        false;
    dmxPatternPaused =
        false;

    updateDmxPatternControls();

    if (clearOutput)
    {
        await sendFullDmxTestFrame();
    }
}

function initializeDmxTestControls()
{
    updateDmxOverrideStatus(
        false,
        0);

    document
        .getElementById('dmxStartAddress')
        .addEventListener(
            'input',
            () =>
            {
                updateDmxTestLabels();
                syncDmxTestFadersFromMonitor();
            });

    for (let i = 0; i < dmxTestFaderCount; i++)
    {
        const fader =
            document.getElementById(
                'dmxCh' + (i + 1));

        fader.addEventListener(
            'input',
            e =>
            {
                const value =
                    parseInt(e.target.value);

                updateDmxTestFaderValue(
                    i,
                    value);

                setDmxChannel(
                    getDmxTestStartAddress() + i,
                    value);
            });
    }

    const holdCheckbox =
        document.getElementById(
            'dmxOverrideHold');

    if (holdCheckbox)
    {
        holdCheckbox.addEventListener(
            'change',
            event =>
            {
                setDmxOverrideTimeoutEnabled(
                    !event.target.checked);
            });
    }

    updateDmxTestLabels();
    updateDmxPatternControls();
}


document
    .getElementById(
        'artnetToDmx')
    .addEventListener(
        'change',
        updateDirectionMode);

document
    .getElementById(
        'dmxToArtnet')
    .addEventListener(
        'change',
        updateDirectionMode);

document
    .getElementById(
        'liveProtocol')
    .addEventListener(
        'change',
        updateDirectionMode);
		
document
    .getElementById(
        'ledBrightness')
    .addEventListener(
        'input',
        updateBrightness);


document
    .getElementById('dhcp')
    .addEventListener(
        'change',
        updateIPMode);

document
    .getElementById('staticIp')
    .addEventListener(
        'change',
        updateIPMode);

[
    'firmwareFile',
    'filesystemFile'
].forEach(id =>
{
    const element =
        document.getElementById(id);

    if (element)
    {
        element.addEventListener(
            'change',
            updateOtaButtons);
    }
});

loadAuthStatus();
loadStatus();
loadConfig();
refreshEventLog();
createDMXMonitor();
initializeTheme();
initializeDmxTestControls();

const ws =
    new WebSocket(
        `ws://${window.location.hostname}:81`);

ws.onopen =
    () =>
{
    console.log(
        "WebSocket connected");
};

ws.onmessage =
    (event) =>
{
    const data =
        JSON.parse(
            event.data);

	if(data.dmx)
	{
		for(let i=0;i<32;i++)
		{
            dmxMonitorSnapshot[i] =
                data.dmx[i];

			document.getElementById(
				'dmx' + i)
				.textContent =
					String(i + 1)
						.padStart(3,'0')
					+ ': '
					+ data.dmx[i];
		}

        syncDmxTestFadersFromMonitor();
	}

    if(data.dmxTestOverride !== undefined)
    {
            updateDmxOverrideStatus(
                data.dmxTestOverride,
                data.dmxTestOverrideRemaining || 0,
                data.dmxTestOverrideTimeoutEnabled !== false);
    }
	
	const detectButton =
    document.getElementById(
        'detectNodeButton');

	if(data.squawking !== undefined)
	{
		detectButton.textContent =
			data.squawking
				? 'Locate On'
				: 'Locate';

		if(data.squawking)
		{
			detectButton.classList.add(
				'activeLocate');
		}
		else
		{
			detectButton.classList.remove(
				'activeLocate');
		}
	}
	
	if(data.leds)
	{
		setIndicator(
			'wifiIndicator',
			data.leds.network);

		setIndicator(
			'artnetIndicator',
			data.leds.activity);
	}

	// LED transitions are also sent as small, LED-only messages. Do not
	// overwrite status fields with missing values in those messages.
	if(data.uptime === undefined)
	{
		return;
	}

    updateHardwareStatus(data);
    updateDetailedDiagnostics(data);
    updateStatusMessages(data);

    updateDashboardRuntime(data);

    document.getElementById(
        'uptime')
        .textContent =
            formatUptime(
                data.uptime);
};

setInterval(
    () =>
    {
        if (!restartInProgress && !connectionRecoveryInProgress)
        {
            loadStatus();
        }
    },
    statusPollInterval
);

setInterval(
    () =>
    {
        if (connectionOnline && !restartInProgress)
        {
            refreshArtNetSubscribers();
        }
    },
    2500
);
