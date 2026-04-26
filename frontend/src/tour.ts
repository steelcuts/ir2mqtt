import Shepherd from 'shepherd.js';
 
type ShepherdTour = InstanceType<typeof Shepherd.Tour>;
// Falls du spezifische Typen von Shepherd importieren kannst, tue dies hier. 
// Standardmäßig exportiert shepherd.js oft nur die Klasse/Namespace.
import { useCommonStore } from './stores/common';
import { useAutomationsStore } from './stores/automations';
import { useDeviceStore, isButtonValid } from './stores/devices';
import { useSettingsStore } from './stores/settings';
import { useBridgeStore } from './stores/bridges';
import { useIrdbStore, type IrdbStatus, type IrDbItem } from './stores/irdb';
import { t } from './i18n';

// Global tour instance
export let tour: ShepherdTour | undefined;

// Flash loop for tour demonstrations
let flashLoopHandle: ReturnType<typeof setInterval> | undefined;

function startFlashLoop(deviceStore: ReturnType<typeof useDeviceStore>, buttonId: string): void {
    if (flashLoopHandle !== undefined) {
        clearInterval(flashLoopHandle);
        flashLoopHandle = undefined;
    }
    let phase = 0;
    const phases = [
        deviceStore.flashingSendButtons,
        deviceStore.flashingReceiveButtons,
        deviceStore.flashingIgnoredButtons,
    ];
    const tick = () => {
        phases.forEach(p => p.delete(buttonId));
        phases[phase].add(buttonId);
        phase = (phase + 1) % phases.length;
    };
    tick();
    flashLoopHandle = setInterval(tick, 1800);
}

function stopFlashLoop(deviceStore: ReturnType<typeof useDeviceStore>, buttonId: string): void {
    if (flashLoopHandle !== undefined) {
        clearInterval(flashLoopHandle);
        flashLoopHandle = undefined;
    }
    deviceStore.flashingSendButtons.delete(buttonId);
    deviceStore.flashingReceiveButtons.delete(buttonId);
    deviceStore.flashingIgnoredButtons.delete(buttonId);
}

// Hilfstypen
interface TourButton {
    text: string;
    action: (this: ShepherdTour) => void;
    classes: string;
}

interface CreateDeviceTourOptions {
    isFirstDevice?: boolean;
    onlyModal?: boolean;
}

interface CreateAutomationTourOptions {
    isFirstAutomation?: boolean;
    onlyModal?: boolean;
}

/**
 * Waits for an element to appear in the DOM and become visible.
 */
function waitForElement(selector: string): Promise<HTMLElement> {
    return new Promise(resolve => {
        const check = () => {
            const element = document.querySelector(selector);
            if (element instanceof HTMLElement && (element.offsetWidth > 0 || element.offsetHeight > 0 || element.getClientRects().length > 0)) {
                resolve(element);
            } else {
                setTimeout(check, 50);
            }
        };
        check();
    });
}

/**
 * Switches the view via the CommonStore and waits for rendering.
 */
function switchView(viewName: string): Promise<void> {
    const commonStore = useCommonStore();
    return new Promise((resolve) => {
        commonStore.activeView = viewName;
        // Wait for the header of the new view to be rendered
        waitForElement(`[data-tour-id="view-title"]`).then((header) => {
            const expectedText = t('nav.' + viewName.toLowerCase().replace(/_|\s/g, ''));
            if (header && header.textContent && header.textContent.includes(expectedText)) {
                resolve();
            } else {
                // It might be a different view, let's wait a bit more
                setTimeout(() => switchView(viewName).then(resolve), 100);
            }
        });
    });
}

export function startTour(): void {
  if (tour && tour.isActive()) {
    tour.cancel();
  }

  tour = new Shepherd.Tour({
    useModalOverlay: true,
    defaultStepOptions: {
      scrollTo: { behavior: 'smooth', block: 'center' },
      cancelIcon: {
        enabled: true
      },
    }
  });

  const buttons: Record<string, TourButton> = {
      back: { text: t('tour.btn.back'), action: tour.back, classes: 'shepherd-button-secondary' },
      next: { text: t('tour.btn.next'), action: tour.next, classes: 'shepherd-button-primary' },
      cancel: { text: t('tour.btn.cancel'), action: tour.cancel, classes: 'shepherd-button-secondary' },
      start: { text: t('tour.btn.startTour'), action: tour.next, classes: 'shepherd-button-primary' },
      done: { text: t('tour.btn.done'), action: tour.complete, classes: 'shepherd-button-primary' }
  };

  tour.addStep({
    id: 'welcome',
    title: t('tour.main.welcome.title'),
    text: t('tour.main.welcome.text'),
    buttons: [ buttons.cancel, buttons.start ]
  });

  tour.addStep({
    id: 'nav-pinning',
    title: t('tour.main.nav.title'),
    text: t('tour.main.nav.text'),
    attachTo: { element: '[data-tour-id="main-icon"]', on: 'right' },
    buttons: [ buttons.back, buttons.next ],
  });

  tour.addStep({
      id: 'devices-overview',
      title: t('tour.main.devices.title'),
      text: t('tour.main.devices.text'),
      attachTo: { element: '[data-tour-id="view-title"]', on: 'right' },
      beforeShowPromise: () => switchView('Devices'),
      buttons: [ buttons.back, buttons.next ],
  });

  tour.addStep({
    id: 'automations-overview',
    title: t('tour.main.automations.title'),
    text: t('tour.main.automations.text'),
    attachTo: { element: '[data-tour-id="view-title"]', on: 'right' },
    beforeShowPromise: () => switchView('Automations'),
    buttons: [ buttons.back, buttons.next ],
  });

  tour.addStep({
    id: 'bridges-overview',
    title: t('tour.main.bridges.title'),
    text: t('tour.main.bridges.text'),
    attachTo: { element: '[data-tour-id="view-title"]', on: 'right' },
    beforeShowPromise: () => switchView('Bridges'),
    buttons: [ buttons.back, buttons.next ],
  });

  tour.addStep({
    id: 'settings-overview',
    title: t('tour.main.settings.title'),
    text: t('tour.main.settings.text'),
    attachTo: { element: '[data-tour-id="view-title"]', on: 'right' },
    beforeShowPromise: () => switchView('Settings'),
    buttons: [ buttons.back, buttons.next ],
  });

  tour.addStep({
    id: 'irdb-overview',
    title: t('tour.main.irdb.title'),
    text: t('tour.main.irdb.text'),
    attachTo: { element: '[data-tour-id="nav-IR_DB"]', on: 'right' },
    buttons: [ buttons.back, buttons.next ],
  });

  tour.addStep({
    id: 'finish',
    title: t('tour.main.finish.title'),
    text: t('tour.main.finish.text'),
    buttons: [ buttons.done ]
  });

  if (tour) {
      tour.on('complete', () => {
        localStorage.setItem('ir2mqtt-main-tour-completed', 'true');
      });
      tour.on('cancel', () => {
        localStorage.setItem('ir2mqtt-main-tour-completed', 'true');
      });

      tour.start();
  }
}

export function startDeviceModalTour(): void {
    startCreateDeviceTour({ onlyModal: true });
}

export function startAutomationModalTour(): void {
    startCreateAutomationTour({ onlyModal: true });
}

export function startButtonModalTour(): void {
    const settingsStore = useSettingsStore();

    const tour = new Shepherd.Tour({
      useModalOverlay: true,
      defaultStepOptions: {
        scrollTo: { behavior: 'smooth', block: 'center' },
        cancelIcon: { enabled: true },
      }
    });

    const buttons: Record<string, TourButton> = {
        back: { text: t('tour.btn.back'), action: tour.back, classes: 'shepherd-button-secondary' },
        next: { text: t('tour.btn.next'), action: tour.next, classes: 'shepherd-button-primary' },
        done: { text: t('tour.btn.done'), action: tour.complete, classes: 'shepherd-button-primary' }
    };

    tour.addStep({
        id: 'btn-intro',
        title: t('tour.device.btnIntro.title'),
        text: t('tour.device.btnIntro.text'),
        buttons: [ buttons.next ]
    });

    tour.addStep({
        id: 'btn-db',
        title: t('tour.device.btnDb.title'),
        text: t('tour.device.btnDb.text'),
        attachTo: { element: '[data-tour-id="button-browse-db"]', on: 'bottom' },
        buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'btn-name',
        title: t('tour.device.btnName.title'),
        text: t('tour.device.btnName.text'),
        attachTo: { element: '[data-tour-id="button-name-input"]', on: 'bottom' },
        buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'btn-icon',
        title: t('tour.device.btnIcon.title'),
        text: t('tour.device.btnIcon.text'),
        attachTo: { element: '[data-tour-id="button-icon-picker"]', on: 'bottom' },
        buttons: [ buttons.back, buttons.next ]
    });

    if (settingsStore.appMode === 'home_assistant') {
        tour.addStep({
            id: 'btn-ha',
            title: t('tour.device.btnHa.title'),
            text: t('tour.device.btnHa.text'),
            attachTo: { element: '[data-tour-id="button-ha-section"]', on: 'top' },
            buttons: [ buttons.back, buttons.next ]
        });
    } else {
        tour.addStep({
            id: 'btn-standalone',
            title: t('tour.device.btnStandalone.title'),
            text: t('tour.device.btnStandalone.text'),
            attachTo: { element: '[data-tour-id="button-standalone-section"]', on: 'top' },
            buttons: [ buttons.back, buttons.next ]
        });
    }

    tour.addStep({
        id: 'btn-code',
        title: t('tour.device.btnCode.title'),
        text: t('tour.device.btnCode.text'),
        attachTo: { element: '[data-tour-id="button-ir-code-section"]', on: 'top' },
        buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'btn-save',
        title: t('tour.device.btnSave.title'),
        text: t('tour.device.btnSave.text'),
        attachTo: { element: '[data-tour-id="button-save-button"]', on: 'top' },
        buttons: [ buttons.back, buttons.done ]
    });

    tour.start();
}

function startCreateDeviceTour({ isFirstDevice = false, onlyModal = false }: CreateDeviceTourOptions = {}): void {
    const tour = new Shepherd.Tour({
      useModalOverlay: true,
      defaultStepOptions: {
        scrollTo: { behavior: 'smooth', block: 'center' },
        cancelIcon: { enabled: true },
      }
    });
  
    const buttons: Record<string, TourButton> = {
        back: { text: t('tour.btn.back'), action: tour.back, classes: 'shepherd-button-secondary' },
        next: { text: t('tour.btn.next'), action: tour.next, classes: 'shepherd-button-primary' },
        done: { text: t('tour.btn.done'), action: tour.complete, classes: 'shepherd-button-primary' }
    };

    if (!onlyModal) {
        if (isFirstDevice) {
            tour.addStep({
                id: 'dev-intro-first',
                title: t('tour.device.introFirst.title'),
                text: t('tour.device.introFirst.text'),
                buttons: [ { text: t('tour.btn.start'), action: tour.next, classes: 'shepherd-button-primary' } ]
            });
            tour.addStep({
                id: 'dev-no-devices',
                title: t('tour.device.noDevices.title'),
                text: t('tour.device.noDevices.text'),
                attachTo: { element: '[data-tour-id="no-devices-message"]', on: 'bottom' },
                beforeShowPromise: () => waitForElement('[data-tour-id="no-devices-message"]'),
                buttons: [ buttons.next ]
            });
        } else {
            tour.addStep({
                id: 'dev-intro',
                title: t('tour.device.intro.title'),
                text: t('tour.device.intro.text'),
                buttons: [ { text: t('tour.btn.start'), action: tour.next, classes: 'shepherd-button-primary' } ]
            });
        }

        tour.addStep({
            id: 'dev-open-modal',
            title: t('tour.device.addDevice.title'),
            text: t('tour.device.addDevice.text'),
            attachTo: { element: '[data-tour-id="add-device-button"]', on: 'left' },
            beforeShowPromise: () => waitForElement('[data-tour-id="add-device-button"]'),
            advanceOn: { selector: '[data-tour-id="add-device-button"]', event: 'click' },
            buttons: [ buttons.back ]
        });
    }

    tour.addStep({
        id: 'dev-init-device',
        title: t('tour.device.init.title'),
        text: t('tour.device.init.text'),
        scrollTo: false,
        attachTo: { element: '[data-tour-id="device-init-section"]', on: 'bottom' },
        beforeShowPromise: () => waitForElement('[data-tour-id="device-init-section"]'),
        buttons: onlyModal ? [ buttons.next ] : [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'dev-name',
        title: t('tour.device.name.title'),
        text: t('tour.device.name.text'),
        scrollTo: false,
        attachTo: { element: '[data-tour-id="device-name-input"]', on: 'bottom' },
        buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'dev-icon',
        title: t('tour.device.icon.title'),
        text: t('tour.device.icon.text'),
        scrollTo: false,
        attachTo: { element: '[data-tour-id="device-icon-picker"]', on: 'bottom' },
        buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'dev-target-bridges',
        title: t('tour.device.targetBridges.title'),
        text: t('tour.device.targetBridges.text'),
        scrollTo: false,
        attachTo: { element: '[data-tour-id="device-target-bridges"]', on: 'top' },
        buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'dev-allowed-bridges',
        title: t('tour.device.allowedBridges.title'),
        text: t('tour.device.allowedBridges.text'),
        scrollTo: false,
        attachTo: { element: '[data-tour-id="device-allowed-bridges"]', on: 'top' },
        buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'dev-save',
        title: t('tour.device.save.title'),
        text: t('tour.device.save.text'),
        scrollTo: false,
        attachTo: { element: '[data-tour-id="device-save-button"]', on: 'top' },
        buttons: [ 
            buttons.back,
            {
                text: t('tour.btn.finishTour'),
                action: tour.complete,
                classes: 'shepherd-button-primary'
            }
        ]
    });

    tour.start();
}

function startExploreDeviceTour(): void {
    const deviceStore = useDeviceStore();

    // Collapse all expanded devices before starting the tour
    deviceStore.devices.forEach(device => {
        if (deviceStore.isDeviceExpanded(device.id)) {
            deviceStore.toggleDevice(device.id);
        }
    });

    const tour = new Shepherd.Tour({
      useModalOverlay: true,
      defaultStepOptions: {
        scrollTo: { behavior: 'smooth', block: 'center' },
        cancelIcon: { enabled: true },
      }
    });
  
    const buttons: Record<string, TourButton> = {
        back: { text: t('tour.btn.back'), action: tour.back, classes: 'shepherd-button-secondary' },
        next: { text: t('tour.btn.next'), action: tour.next, classes: 'shepherd-button-primary' },
        done: { text: t('tour.btn.done'), action: tour.complete, classes: 'shepherd-button-primary' }
    };
    const firstDevice = deviceStore.devices.length > 0 ? deviceStore.devices[0] : null;

    if (!firstDevice) {
        tour.addStep({
            id: 'exp-no-devices',
            title: t('tour.device.expNoDevices.title'),
            text: t('tour.device.expNoDevices.text'),
            buttons: [buttons.done]
        });
        tour.start();
        return;
    }

    tour.addStep({
        id: 'exp-intro',
        title: t('tour.device.expIntro.title'),
        text: t('tour.device.expIntro.text'),
        buttons: [ { text: t('tour.btn.start'), action: tour.next, classes: 'shepherd-button-primary' } ]
    });

    tour.addStep({
        id: 'exp-card',
        title: t('tour.device.expCard.title'),
        text: t('tour.device.expCard.text'),
        attachTo: { element: '[data-tour-id="device-card"]', on: 'top' },
        beforeShowPromise: () => waitForElement('[data-tour-id="device-card"]'),
        buttons: [buttons.back, buttons.next]
    });

    tour.addStep({
        id: 'exp-device-actions',
        title: t('tour.device.expActions.title'),
        text: t('tour.device.expActions.text'),
        attachTo: { element: '[data-tour-id="device-card"]:first-of-type [data-tour-id="device-action-buttons"]', on: 'left' },
        beforeShowPromise: () => waitForElement('[data-tour-id="device-card"]:first-of-type [data-tour-id="device-action-buttons"]'),
        buttons: [buttons.back, buttons.next]
    });

    if (firstDevice.buttons && firstDevice.buttons.length > 0) {
        tour.addStep({
            id: 'exp-collapsed-buttons',
            title: t('tour.device.expCollapsed.title'),
            text: t('tour.device.expCollapsed.text'),
            attachTo: { element: '[data-tour-id="device-card"]:first-of-type .flex-wrap', on: 'bottom' },
            beforeShowPromise: () => {
                return new Promise<void>(resolve => {
                    if (deviceStore.isDeviceExpanded(firstDevice.id)) {
                        deviceStore.toggleDevice(firstDevice.id);
                    }
                    // Need to wait for the collapse animation to finish
                    setTimeout(() => {
                        waitForElement('[data-tour-id="device-card"]:first-of-type .flex-wrap').then(() => resolve());
                    }, 300);
                });
            },
            when: {
                show: () => {
                    const buttonToFlash = firstDevice.buttons.find(b => isButtonValid(b));
                    if (buttonToFlash) {
                        deviceStore.flashingReceiveButtons.add(buttonToFlash.id);
                        setTimeout(() => {
                            deviceStore.flashingReceiveButtons.delete(buttonToFlash.id);
                        }, 1000); // match animation duration
                    }
                }
            },
            buttons: [buttons.back, buttons.next]
        });
    }
    
    tour.addStep({
        id: 'exp-expand',
        title: t('tour.device.expExpand.title'),
        text: t('tour.device.expExpand.text'),
        attachTo: { element: '[data-tour-id="device-card"]:first-of-type [data-tour-id="device-expand-toggle"]', on: 'right' },
        beforeShowPromise: () => {
            return new Promise<void>(resolve => {
                if (deviceStore.isDeviceExpanded(firstDevice.id)) {
                    deviceStore.toggleDevice(firstDevice.id);
                }
                waitForElement('[data-tour-id="device-card"]:first-of-type [data-tour-id="device-expand-toggle"]').then(() => resolve());
            });
        },
        advanceOn: { selector: '[data-tour-id="device-card"]:first-of-type [data-tour-id="device-expand-toggle"]', event: 'click' },
        buttons: [buttons.back]
    });
    
    if (firstDevice.buttons && firstDevice.buttons.length > 0) {
        tour.addStep({
            id: 'exp-add-button',
            title: t('tour.device.expAddBtn.title'),
            text: t('tour.device.expAddBtn.text'),
            attachTo: { element: '[data-tour-id="device-card"]:first-of-type [data-tour-id="add-button-to-device"]', on: 'right' },
            beforeShowPromise: () => waitForElement('[data-tour-id="device-card"]:first-of-type [data-tour-id="add-button-to-device"]'),
            buttons: [buttons.back, buttons.next]
        });

        tour.addStep({
            id: 'exp-button-card',
            title: t('tour.device.expBtnCard.title'),
            text: t('tour.device.expBtnCard.text'),
            attachTo: { element: '[data-tour-id="device-card"]:first-of-type .grid .group', on: 'right' },
            beforeShowPromise: () => waitForElement('[data-tour-id="device-card"]:first-of-type .grid .group'),
            buttons: [buttons.back, buttons.next]
        });

        const buttonToFlash = firstDevice.buttons.find(b => isButtonValid(b));
        if (buttonToFlash) {
            tour.addStep({
                id: 'exp-flash-demo',
                title: t('tour.device.expFlashDemo.title'),
                text: t('tour.device.expFlashDemo.text'),
                attachTo: { element: '[data-tour-id="device-card"]:first-of-type .grid .group', on: 'right' },
                beforeShowPromise: () => waitForElement('[data-tour-id="device-card"]:first-of-type .grid .group'),
                when: {
                    show: () => startFlashLoop(deviceStore, buttonToFlash.id),
                    hide: () => stopFlashLoop(deviceStore, buttonToFlash.id),
                },
                buttons: [buttons.back, buttons.next]
            });
        }
    } else {
         tour.addStep({
            id: 'exp-add-first-button',
            title: t('tour.device.expAddFirst.title'),
            text: t('tour.device.expAddFirst.text'),
            attachTo: { element: '[data-tour-id="device-card"]:first-of-type [data-tour-id="add-button-to-device"]', on: 'bottom' },
            beforeShowPromise: () => waitForElement('[data-tour-id="device-card"]:first-of-type [data-tour-id="add-button-to-device"]'),
            buttons: [buttons.back, buttons.next]
        });
    }

    tour.addStep({
        id: 'exp-learn',
        title: t('tour.device.expLearn.title'),
        text: t('tour.device.expLearn.text'),
        attachTo: { element: '[data-tour-id="quick-learn-button"]', on: 'left' },
        beforeShowPromise: () => waitForElement('[data-tour-id="quick-learn-button"]'),
        buttons: [buttons.back, buttons.done]
    });

    tour.start();
}

export async function startDevicesTour(): Promise<void> {
    if (tour && tour.isActive()) {
      tour.cancel();
    }

    await switchView('Devices');
  
    startExploreDeviceTour();
}

export async function startBridgesTour(): Promise<void> {
    const bridgeStore = useBridgeStore();

    if (tour && tour.isActive()) {
      tour.cancel();
    }

    await switchView('Bridges');
  
    tour = new Shepherd.Tour({
      useModalOverlay: true,
      defaultStepOptions: {
        scrollTo: { behavior: 'smooth', block: 'center' },
        cancelIcon: { enabled: true },
      }
    });
  
    const buttons: Record<string, TourButton> = {
        back: { text: t('tour.btn.back'), action: tour.back, classes: 'shepherd-button-secondary' },
        next: { text: t('tour.btn.next'), action: tour.next, classes: 'shepherd-button-primary' },
        done: { text: t('tour.btn.done'), action: tour.complete, classes: 'shepherd-button-primary' }
    };

    tour.addStep({
      id: 'bridge-intro',
      title: t('tour.bridge.intro.title'),
      text: t('tour.bridge.intro.text'),
      buttons: [ { text: t('tour.btn.start'), action: tour.next, classes: 'shepherd-button-primary' } ]
    });

    if (bridgeStore.bridges.length === 0) {
        tour.addStep({
            id: 'bridge-no-bridges',
            title: t('tour.bridge.noBridges.title'),
            text: t('tour.bridge.noBridges.text'),
            attachTo: { element: '[data-tour-id="no-bridges-message"]', on: 'bottom' },
            beforeShowPromise: () => waitForElement('[data-tour-id="no-bridges-message"]'),
            buttons: [ buttons.next ]
        });
    } else {
        const firstBridge = bridgeStore.bridges[0];
        const isConnecting = firstBridge && firstBridge.status === 'connecting';

        tour.addStep({
            id: 'bridge-table',
            title: t('tour.bridge.table.title'),
            text: t('tour.bridge.table.text'),
            attachTo: { element: '[data-tour-id="bridges-table"]', on: 'bottom' },
            beforeShowPromise: () => waitForElement('[data-tour-id="bridges-table"]'),
            buttons: [ buttons.back, buttons.next ]
        });

        tour.addStep({
            id: 'bridge-status',
            title: t('tour.bridge.status.title'),
            text: t('tour.bridge.status.text'),
            attachTo: { element: '[data-tour-id="bridge-status"]', on: 'right' },
            beforeShowPromise: () => waitForElement('[data-tour-id="bridge-status"]'),
            buttons: [ buttons.back, buttons.next ]
        });

        tour.addStep({
            id: 'bridge-info',
            title: t('tour.bridge.info.title'),
            text: t('tour.bridge.info.text'),
            attachTo: { element: '[data-tour-id="bridge-info"]', on: 'bottom' },
            beforeShowPromise: () => waitForElement('[data-tour-id="bridge-info"]'),
            buttons: [ buttons.back, buttons.next ]
        });

        if (!isConnecting) {
            tour.addStep({
                id: 'bridge-protocols',
                title: t('tour.bridge.protocols.title'),
                text: t('tour.bridge.protocols.text'),
                attachTo: { element: '[data-tour-id="bridge-protocols"]', on: 'left' },
                beforeShowPromise: () => waitForElement('[data-tour-id="bridge-protocols"]'),
                buttons: [ buttons.back, buttons.next ]
            });

            tour.addStep({
                id: 'bridge-history',
                title: t('tour.bridge.history.title'),
                text: t('tour.bridge.history.text'),
                attachTo: { element: '[data-tour-id="bridge-history-btn"]', on: 'left' },
                beforeShowPromise: () => waitForElement('[data-tour-id="bridge-history-btn"]'),
                buttons: [ buttons.back, buttons.next ]
            });
        } else {
            tour.addStep({
                id: 'bridge-connecting-info',
                title: t('tour.bridge.connecting.title'),
                text: t('tour.bridge.connecting.text'),
                attachTo: { element: '[data-tour-id="bridge-status"]', on: 'right' },
                buttons: [ buttons.back, buttons.next ]
            });
        }

        tour.addStep({
            id: 'bridge-actions',
            title: t('tour.bridge.actions.title'),
            text: t('tour.bridge.actions.text'),
            attachTo: { element: '[data-tour-id="bridge-delete-btn"]', on: 'left' },
            beforeShowPromise: () => waitForElement('[data-tour-id="bridge-delete-btn"]'),
            buttons: [ buttons.back, buttons.next ]
        });

        if (!isConnecting) {
            tour.addStep({
                id: 'bridge-edit-intro',
                title: t('tour.bridge.edit.title'),
                text: t('tour.bridge.edit.text'),
                attachTo: { element: '[data-tour-id="bridge-edit-btn"]', on: 'left' },
                beforeShowPromise: () => waitForElement('[data-tour-id="bridge-edit-btn"]'),
                advanceOn: { selector: '[data-tour-id="bridge-edit-btn"]', event: 'click' },
                buttons: [ buttons.back ]
            });

            tour.addStep({
                id: 'bridge-settings-echo',
                title: t('tour.bridge.echo.title'),
                text: t('tour.bridge.echo.text'),
                attachTo: { element: '[data-tour-id="bridge-settings-panel"]', on: 'bottom' },
                beforeShowPromise: () => waitForElement('[data-tour-id="bridge-settings-panel"]'),
                scrollTo: false,
                buttons: [ buttons.next ]
            });
        }
    }

    tour.addStep({
        id: 'bridge-add-serial-btn',
        title: t('tour.bridge.addSerial.title'),
        text: t('tour.bridge.addSerial.text'),
        attachTo: { element: '[data-tour-id="add-serial-bridge-btn"]', on: 'left' },
        beforeShowPromise: () => waitForElement('[data-tour-id="add-serial-bridge-btn"]'),
        advanceOn: { selector: '[data-tour-id="add-serial-bridge-btn"]', event: 'click' },
        buttons: [ buttons.back ]
    });

    tour.addStep({
        id: 'bridge-add-serial-modal',
        title: t('tour.bridge.serialModal.title'),
        text: t('tour.bridge.serialModal.text'),
        attachTo: { element: '[data-tour-id="add-serial-bridge-modal"]', on: 'bottom' },
        beforeShowPromise: () => waitForElement('[data-tour-id="add-serial-bridge-modal"]'),
        when: {
            hide: () => {
                const closeBtn = document.querySelector<HTMLElement>('[data-tour-id="add-serial-bridge-modal"] button');
                if (closeBtn) closeBtn.click();
            }
        },
        buttons: [ buttons.back, buttons.done ]
    });

    tour.start();
}

function setTriggerType(type: 'single' | 'multi' | 'sequence'): Promise<void> {
    const automationsStore = useAutomationsStore();
    return new Promise(resolve => {
        if (automationsStore.editingAutomation && automationsStore.editingAutomation.triggers && automationsStore.editingAutomation.triggers.length > 0) {
            automationsStore.editingAutomation.triggers[0].type = type;
        }
        // Give Vue a moment to render the v-if blocks
        setTimeout(resolve, 300);
    });
}

function startCreateAutomationTour({ isFirstAutomation = false, onlyModal = false }: CreateAutomationTourOptions = {}): void {
    const automationsStore = useAutomationsStore();
    const deviceStore = useDeviceStore();
    const settingsStore = useSettingsStore();

    const tour = new Shepherd.Tour({
      useModalOverlay: true,
      defaultStepOptions: {
        scrollTo: { behavior: 'smooth', block: 'center' },
        cancelIcon: { enabled: true },
      }
    });
  
    const buttons: Record<string, TourButton> = {
        back: { text: t('tour.btn.back'), action: tour.back, classes: 'shepherd-button-secondary' },
        next: { text: t('tour.btn.next'), action: tour.next, classes: 'shepherd-button-primary' },
        done: { text: t('tour.btn.done'), action: tour.complete, classes: 'shepherd-button-primary' }
    };
  
    if (!onlyModal) {
        if (isFirstAutomation) {
            tour.addStep({
                id: 'auto-intro-first',
                title: t('tour.auto.introFirst.title'),
                text: t('tour.auto.introFirst.text'),
                buttons: [ { text: t('tour.btn.start'), action: tour.next, classes: 'shepherd-button-primary' } ]
            });
        } else {
            tour.addStep({
                id: 'auto-intro',
                title: t('tour.auto.intro.title'),
                text: t('tour.auto.intro.text'),
                buttons: [ { text: t('tour.btn.start'), action: tour.next, classes: 'shepherd-button-primary' } ]
            });
        }

        if (deviceStore.devices.length === 0) {
            tour.addStep({
                id: 'auto-no-devices',
                title: t('tour.auto.noDevices.title'),
                text: t('tour.auto.noDevices.text'),
                attachTo: { element: '[data-tour-id="create-automation-button-disabled"]', on: 'left' },
                beforeShowPromise: () => waitForElement('[data-tour-id="create-automation-button-disabled"]'),
                buttons: [ buttons.back, buttons.next ]
            });
            tour.addStep({
                id: 'auto-goto-devices',
                title: t('tour.auto.gotoDevices.title'),
                text: t('tour.auto.gotoDevices.text'),
                attachTo: { element: '[data-tour-id="nav-Devices"]', on: 'right' },
                buttons: [
                    buttons.back,
                    {
                        text: t('tour.btn.goToDevices'),
                        action: function(this: ShepherdTour) {
                            this.cancel();
                            switchView('Devices');
                        },
                        classes: 'shepherd-button-primary'
                    }
                ]
            });
            tour.start();
            return;
        } else {
            tour.addStep({
                id: 'auto-open-modal',
                title: t('tour.auto.openModal.title'),
                text: t('tour.auto.openModal.text'),
                attachTo: { element: '[data-tour-id="create-automation-button"]', on: 'left' },
                beforeShowPromise: () => waitForElement('[data-tour-id="create-automation-button"]'),
                advanceOn: { selector: '[data-tour-id="create-automation-button"]', event: 'click' },
                buttons: [ buttons.back ]
            });
        }
    }

    // Modal steps
        tour.addStep({
            id: 'auto-name',
            title: t('tour.auto.name.title'),
            text: t('tour.auto.name.text'),
            scrollTo: false,
            attachTo: { element: '[data-tour-id="automation-name-input"]', on: 'bottom' },
            buttons: onlyModal ? [ buttons.next ] : [ buttons.back, buttons.next ]
        });
        tour.addStep({
            id: 'auto-enabled',
            title: t('tour.auto.enabled.title'),
            text: t('tour.auto.enabled.text'),
            scrollTo: false,
            attachTo: { element: '[data-tour-id="automation-enabled-switch"]', on: 'bottom' },
            buttons: [ buttons.back, buttons.next ]
        });
        tour.addStep({
            id: 'auto-trigger-type',
            title: t('tour.auto.triggerType.title'),
            text: t('tour.auto.triggerType.text'),
            scrollTo: false,
            beforeShowPromise: () => setTriggerType('single'),
            attachTo: { element: '[data-tour-id="automation-trigger-type"]', on: 'bottom' },
            buttons: [ buttons.back, buttons.next ]
        });
        tour.addStep({
            id: 'auto-trigger-device',
            title: t('tour.auto.triggerDev.title'),
            text: t('tour.auto.triggerDev.text'),
            scrollTo: false,
            beforeShowPromise: () => setTriggerType('single'),
            attachTo: { element: '[data-tour-id="automation-trigger-device-selection"]', on: 'bottom' },
            buttons: [ buttons.back, buttons.next ]
        });
        tour.addStep({
            id: 'auto-multi-options',
            title: t('tour.auto.multiOpt.title'),
            text: t('tour.auto.multiOpt.text'),
            scrollTo: false,
            beforeShowPromise: () => setTriggerType('multi'),
            attachTo: { element: '[data-tour-id="automation-multi-options"]', on: 'top' },
            buttons: [ buttons.back, buttons.next ]
        });
        tour.addStep({
            id: 'auto-strict-mode',
            title: t('tour.auto.strict.title'),
            text: t('tour.auto.strict.text'),
            scrollTo: false,
            beforeShowPromise: () => setTriggerType('multi'),
            attachTo: { element: '[data-tour-id="automation-strict-mode"]', on: 'bottom' },
            buttons: [ buttons.back, buttons.next ]
        });
        tour.addStep({
            id: 'auto-sequence-options',
            title: t('tour.auto.seqOpt.title'),
            text: t('tour.auto.seqOpt.text'),
            scrollTo: false,
            beforeShowPromise: () => setTriggerType('sequence'),
            attachTo: { element: '[data-tour-id="automation-sequence-options"]', on: 'top' },
            buttons: [ buttons.back, buttons.next ]
        });
        tour.addStep({
            id: 'auto-actions',
            title: t('tour.auto.actions.title'),
            text: t('tour.auto.actions.text'),
            scrollTo: false,
            beforeShowPromise: () => setTriggerType('single'), // Reset to single to clean up UI
            attachTo: { element: '[data-tour-id="automation-actions-section"]', on: 'top' },
            buttons: [ buttons.back, buttons.next ]
        });
        tour.addStep({
            id: 'auto-parallel',
            title: t('tour.auto.parallel.title'),
            text: t('tour.auto.parallel.text'),
            scrollTo: false,
            attachTo: { element: '[data-tour-id="automation-parallel-switch"]', on: 'top' },
            buttons: [ buttons.back, buttons.next ]
        });
        if (settingsStore.appMode === 'home_assistant') {
            tour.addStep({
                id: 'auto-ha',
                title: t('tour.auto.ha.title'),
                text: t('tour.auto.ha.text'),
                scrollTo: false,
                attachTo: { element: '[data-tour-id="automation-ha-section"]', on: 'top' },
                buttons: [ buttons.back, buttons.next ]
            });
        }
        tour.addStep({
            id: 'auto-save',
            title: t('tour.auto.save.title'),
            text: t('tour.auto.save.text'),
            scrollTo: false,
            attachTo: { element: '[data-tour-id="automation-save-button"]', on: 'top' },
            buttons: [ buttons.back, buttons.done ],
            when: {
                hide: () => { automationsStore.editingAutomation = null; }
            }
        });
    tour.start();
}

function startExploreAutomationTour(): void {
    const automationsStore = useAutomationsStore();

    const tour = new Shepherd.Tour({
      useModalOverlay: true,
      defaultStepOptions: {
        scrollTo: { behavior: 'smooth', block: 'center' },
        cancelIcon: { enabled: true },
      }
    });
  
    const buttons: Record<string, TourButton> = {
        back: { text: t('tour.btn.back'), action: tour.back, classes: 'shepherd-button-secondary' },
        next: { text: t('tour.btn.next'), action: tour.next, classes: 'shepherd-button-primary' },
        done: { text: t('tour.btn.done'), action: tour.complete, classes: 'shepherd-button-primary' }
    };

    const firstAutomation = automationsStore.automations.length > 0 ? automationsStore.automations[0] : null;

    if (!firstAutomation) {
        tour.addStep({
            id: 'exp-auto-no-automations',
            title: t('tour.auto.expNoAuto.title'),
            text: t('tour.auto.expNoAuto.text'),
            buttons: [buttons.done]
        });
        tour.start();
        return;
    }

    tour.addStep({
        id: 'exp-auto-intro',
        title: t('tour.auto.expIntro.title'),
        text: t('tour.auto.expIntro.text'),
        buttons: [ { text: t('tour.btn.start'), action: tour.next, classes: 'shepherd-button-primary' } ]
    });

    tour.addStep({
        id: 'exp-auto-card',
        title: t('tour.auto.expCard.title'),
        text: t('tour.auto.expCard.text'),
        attachTo: { element: '[data-tour-id="automation-card"]', on: 'top' },
        beforeShowPromise: () => waitForElement('[data-tour-id="automation-card"]'),
        buttons: [buttons.back, buttons.next]
    });

    tour.addStep({
        id: 'exp-auto-actions',
        title: t('tour.auto.expActions.title'),
        text: t('tour.auto.expActions.text'),
        attachTo: { element: '[data-tour-id="automation-card"]:first-of-type [data-tour-id="automation-action-buttons"]', on: 'left' },
        beforeShowPromise: () => waitForElement('[data-tour-id="automation-card"]:first-of-type [data-tour-id="automation-action-buttons"]'),
        buttons: [buttons.back, buttons.next]
    });

    tour.addStep({
        id: 'exp-auto-flow',
        title: t('tour.auto.expFlow.title'),
        text: t('tour.auto.expFlow.text'),
        attachTo: { element: '[data-tour-id="automation-card"]:first-of-type .overflow-x-auto', on: 'bottom' },
        beforeShowPromise: () => waitForElement('[data-tour-id="automation-card"]:first-of-type .overflow-x-auto'),
        buttons: [buttons.back, buttons.next]
    });

     tour.addStep({
        id: 'exp-auto-running',
        title: t('tour.auto.expRunning.title'),
        text: t('tour.auto.expRunning.text'),
        attachTo: { element: '[data-tour-id="automation-card"]:first-of-type', on: 'top' },
        buttons: [buttons.back, buttons.next]
    });

    tour.addStep({
        id: 'exp-auto-create',
        title: t('tour.auto.expCreate.title'),
        text: t('tour.auto.expCreate.text'),
        attachTo: { element: '[data-tour-id="create-automation-button"]', on: 'left' },
        beforeShowPromise: () => waitForElement('[data-tour-id="create-automation-button"]'),
        buttons: [buttons.back, buttons.done]
    });

    tour.start();
}

export async function startAutomationTour(): Promise<void> {
    const deviceStore = useDeviceStore();

    if (tour && tour.isActive()) {
      tour.cancel();
    }

    await switchView('Automations');
    await deviceStore.fetchDevices();
  
    startExploreAutomationTour();
}

export async function startSettingsTour(): Promise<void> {
    const settingsStore = useSettingsStore();

    if (tour && tour.isActive()) {
      tour.cancel();
    }

    await switchView('Settings');
  
    tour = new Shepherd.Tour({
      useModalOverlay: true,
      defaultStepOptions: {
        scrollTo: { behavior: 'smooth', block: 'center' },
        cancelIcon: { enabled: true },
      }
    });
  
    const buttons: Record<string, TourButton> = {
        back: { text: t('tour.btn.back'), action: tour.back, classes: 'shepherd-button-secondary' },
        next: { text: t('tour.btn.next'), action: tour.next, classes: 'shepherd-button-primary' },
        done: { text: t('tour.btn.done'), action: tour.complete, classes: 'shepherd-button-primary' }
    };

    tour.addStep({
      id: 'settings-intro',
      title: t('tour.settings.intro.title'),
      text: t('tour.settings.intro.text'),
      buttons: [ { text: t('tour.btn.start'), action: tour.next, classes: 'shepherd-button-primary' } ]
    });

    tour.addStep({
      id: 'settings-ui',
      title: t('tour.settings.ui.title'),
      text: t('tour.settings.ui.text'),
      attachTo: { element: '[data-tour-id="settings-ui-card"]', on: 'bottom' },
      beforeShowPromise: () => waitForElement('[data-tour-id="settings-ui-card"]'),
      buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
      id: 'settings-theme',
      title: t('tour.settings.theme.title'),
      text: t('tour.settings.theme.text'),
      attachTo: { element: '[data-tour-id="theme-selector"]', on: 'left' },
      beforeShowPromise: () => waitForElement('[data-tour-id="theme-selector"]'),
      buttons: [ buttons.back, buttons.next ]
    });
    
    tour.addStep({
      id: 'settings-loglevel',
      title: t('tour.settings.loglevel.title'),
      text: t('tour.settings.loglevel.text'),
      attachTo: { element: '[data-tour-id="settings-log-level"]', on: 'left' },
      beforeShowPromise: () => waitForElement('[data-tour-id="settings-log-level"]'),
      buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
      id: 'settings-backend',
      title: t('tour.settings.backend.title'),
      text: t('tour.settings.backend.text'),
      attachTo: { element: '[data-tour-id="settings-backend-card"]', on: 'bottom' },
      beforeShowPromise: () => waitForElement('[data-tour-id="settings-backend-card"]'),
      buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
      id: 'settings-opmode',
      title: t('tour.settings.opmode.title'),
      text: t('tour.settings.opmode.text'),
      attachTo: { element: '[data-tour-id="settings-operating-mode"]', on: 'top' },
      beforeShowPromise: () => waitForElement('[data-tour-id="settings-operating-mode"]'),
      buttons: [ buttons.back, buttons.next ]
    });

    if (settingsStore.appMode === 'standalone') {
        tour.addStep({
          id: 'settings-topic-style',
          title: t('tour.settings.topicStyle.title'),
          text: t('tour.settings.topicStyle.text'),
          attachTo: { element: '[data-tour-id="settings-topic-style"]', on: 'top' },
          beforeShowPromise: () => waitForElement('[data-tour-id="settings-topic-style"]'),
          buttons: [ buttons.back, buttons.next ]
        });
    }

    tour.addStep({
      id: 'settings-mqtt',
      title: t('tour.settings.mqtt.title'),
      text: t('tour.settings.mqtt.text'),
      attachTo: { element: '[data-tour-id="settings-mqtt-card"]', on: 'top' },
      beforeShowPromise: () => waitForElement('[data-tour-id="settings-mqtt-card"]'),
      buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'settings-loopback',
        title: t('tour.settings.loopback.title'),
        text: t('tour.settings.loopback.text'),
        attachTo: { element: '[data-tour-id="settings-loopback-card"]', on: 'top' },
        beforeShowPromise: () => waitForElement('[data-tour-id="settings-loopback-card"]'),
        buttons: [ buttons.back, buttons.next ]
      });

    tour.addStep({
      id: 'settings-config',
      title: t('tour.settings.config.title'),
      text: t('tour.settings.config.text'),
      attachTo: { element: '[data-tour-id="settings-config-card"]', on: 'top' },
      beforeShowPromise: () => waitForElement('[data-tour-id="settings-config-card"]'),
      buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
      id: 'settings-danger',
      title: t('tour.settings.danger.title'),
      text: t('tour.settings.danger.text'),
      attachTo: { element: '[data-tour-id="settings-danger-zone"]', on: 'top' },
      beforeShowPromise: () => waitForElement('[data-tour-id="settings-danger-zone"]'),
      buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'settings-done',
        title: t('tour.settings.done.title'),
        text: t('tour.settings.done.text'),
        buttons: [ buttons.done ]
    });

    tour.start();
}

export async function startIrDbTour(irdbStatus: IrdbStatus, openItem: (file: IrDbItem) => void): Promise<void> {
    const irdbStore = useIrdbStore();
    const commonStore = useCommonStore();

    if (tour && tour.isActive()) {
      tour.cancel();
    }
  
    tour = new Shepherd.Tour({
      useModalOverlay: true,
      defaultStepOptions: {
        scrollTo: { behavior: 'smooth', block: 'center' },
        cancelIcon: { enabled: true },
      }
    });
  
    const buttons: Record<string, TourButton> = {
        back: { text: t('tour.btn.back'), action: tour.back, classes: 'shepherd-button-secondary' },
        next: { text: t('tour.btn.next'), action: tour.next, classes: 'shepherd-button-primary' },
        done: { text: t('tour.btn.done'), action: tour.complete, classes: 'shepherd-button-primary' }
    };

    tour.addStep({
      id: 'irdb-intro',
      title: t('tour.irdb.intro.title'),
      text: t('tour.irdb.intro.text'),
      buttons: [ { text: t('tour.btn.start'), action: tour.next, classes: 'shepherd-button-primary' } ]
    });

    if (!irdbStatus.exists) {
        tour.addStep({
          id: 'irdb-no-db',
          title: t('tour.irdb.noDb.title'),
          text: t('tour.irdb.noDb.text'),
          attachTo: { element: '[data-tour-id="irdb-no-db-message"]', on: 'bottom' },
          beforeShowPromise: () => waitForElement('[data-tour-id="irdb-no-db-message"]'),
          buttons: [ buttons.back, buttons.next ]
        });

        tour.addStep({
            id: 'irdb-download',
            title: t('tour.irdb.download.title'),
            text: t('tour.irdb.download.text'),
            attachTo: { element: '[data-tour-id="irdb-download-button"]', on: 'bottom' },
            buttons: [ buttons.back, buttons.done ]
        });

    } else {
        tour.addStep({
          id: 'irdb-search',
          title: t('tour.irdb.search.title'),
          text: t('tour.irdb.search.text'),
          attachTo: { element: '[data-tour-id="irdb-search-input"]', on: 'bottom' },
          beforeShowPromise: () => waitForElement('[data-tour-id="irdb-search-input"]'),
          buttons: [ buttons.back, buttons.next ]
        });

        tour.addStep({
            id: 'irdb-browse',
            title: t('tour.irdb.browse.title'),
            text: t('tour.irdb.browse.text'),
            attachTo: { element: '[data-tour-id="irdb-file-list"]', on: 'bottom' },
            beforeShowPromise: () => waitForElement('[data-tour-id="irdb-file-list"]'),
            buttons: [ buttons.back, buttons.next ]
        });

        tour.addStep({
            id: 'irdb-navigating',
            title: t('tour.irdb.navigating.title'),
            text: t('tour.irdb.navigating.text'),
            buttons: [],
            when: {
                show: async () => {
                    const findFirstFile = async (path: string): Promise<IrDbItem | null> => {
                        const items = await irdbStore.browseIrdb(path);
                        if (!items) return null;
                        
                        const file = items.find((item: IrDbItem) => item.type === 'file');
                        if (file) return file;

                        const dir = items.find((item: IrDbItem) => item.type === 'dir');
                        if (dir) return findFirstFile(dir.path);
                        
                        return null;
                    };
                    
                    const fileToOpen = await findFirstFile('');
                    if (fileToOpen) {
                        openItem(fileToOpen);
                        tour?.next();
                    } else {
                        commonStore.addFlashMessage(t('tour.irdb.demoError'), 'error');
                        tour?.cancel();
                    }
                }
            }
        });

        tour.addStep({
            id: 'irdb-buttons',
            title: t('tour.irdb.buttons.title'),
            text: t('tour.irdb.buttons.text'),
            attachTo: { element: '[data-tour-id="irdb-first-button"]', on: 'top' },
            beforeShowPromise: () => waitForElement('[data-tour-id="irdb-first-button"]'),
            buttons: [ buttons.back, buttons.next ]
        });

        tour.addStep({
            id: 'irdb-import',
            title: t('tour.irdb.import.title'),
            text: t('tour.irdb.import.text'),
            attachTo: { element: '[data-tour-id="irdb-first-button"]', on: 'top' },
            buttons: [ buttons.back, buttons.done ]
        });
    }

    tour.start();
}

export function startConfigTransferTour(): void {
    const tour = new Shepherd.Tour({
      useModalOverlay: true,
      defaultStepOptions: {
        scrollTo: { behavior: 'smooth', block: 'center' },
        cancelIcon: { enabled: true },
      }
    });
  
    const buttons: Record<string, TourButton> = {
        back: { text: t('tour.btn.back'), action: tour.back, classes: 'shepherd-button-secondary' },
        next: { text: t('tour.btn.next'), action: tour.next, classes: 'shepherd-button-primary' },
        done: { text: t('tour.btn.done'), action: tour.complete, classes: 'shepherd-button-primary' }
    };

    const clickElement = (selector: string): Promise<void> => {
        return new Promise(resolve => {
            const el = document.querySelector(selector) as HTMLElement | null;
            if (el) el.click();
            setTimeout(resolve, 300);
        });
    };

    tour.addStep({
        id: 'config-intro',
        title: t('tour.config.intro.title'),
        text: t('tour.config.intro.text'),
        attachTo: { element: '[data-tour-id="config-transfer-modal"]', on: 'top' },
        buttons: [ buttons.next ]
    });

    tour.addStep({
        id: 'config-mode',
        title: t('tour.config.mode.title'),
        text: t('tour.config.mode.text'),
        attachTo: { element: '[data-tour-id="config-mode-switch"]', on: 'bottom' },
        buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'config-export-tree',
        title: t('tour.config.expTree.title'),
        text: t('tour.config.expTree.text'),
        attachTo: { element: '[data-tour-id="config-tree-view"]', on: 'top' },
        beforeShowPromise: () => clickElement('[data-tour-id="config-mode-export"]'),
        buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'config-export-action',
        title: t('tour.config.expAction.title'),
        text: t('tour.config.expAction.text'),
        attachTo: { element: '[data-tour-id="config-action-button"]', on: 'top' },
        buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'config-import-mode',
        title: t('tour.config.impMode.title'),
        text: t('tour.config.impMode.text'),
        attachTo: { element: '[data-tour-id="config-mode-import"]', on: 'bottom' },
        beforeShowPromise: () => clickElement('[data-tour-id="config-mode-import"]'),
        buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'config-import-file',
        title: t('tour.config.impFile.title'),
        text: t('tour.config.impFile.text'),
        attachTo: { element: '[data-tour-id="config-file-input"]', on: 'bottom' },
        buttons: [ buttons.back, buttons.next ]
    });

    tour.addStep({
        id: 'config-import-action',
        title: t('tour.config.impAction.title'),
        text: t('tour.config.impAction.text'),
        attachTo: { element: '[data-tour-id="config-action-button"]', on: 'top' },
        buttons: [ buttons.back, buttons.done ]
    });

    tour.start();
}