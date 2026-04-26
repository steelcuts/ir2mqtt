// This file contains TypeScript interfaces that correspond to the Pydantic
// models in the backend's `models.py`. Keeping them in sync is crucial.

// Loose payload type - each protocol uses a subset of fields
export type IRCodePayload = Record<string, string | number | number[] | boolean | null | undefined>;

export interface IRCode {
  protocol: string;
  payload: IRCodePayload;
  raw_tolerance?: number;
}

export interface IRButton {
  id: string;
  name: string;
  icon?: string;
  code: IRCode | null;
  is_output: boolean;
  is_input: boolean;
  is_event: boolean;
  input_mode?: 'momentary' | 'toggle' | 'timed';
  input_off_delay_s?: number;
  ordering?: number;
}

export interface IRDevice {
  id: string;
  name: string;
  icon: string;
  buttons: IRButton[];
  target_bridges: string[];
  allowed_bridges: string[];
  ordering?: number;
}

export interface IRAutomationAction {
  type: string;
  device_id?: string | null;
  button_id?: string | null;
  target?: string | null;
  delay_ms?: number | null;
  event_name?: string | null;
}

export interface IRAutomationTrigger {
  type: string;
  device_id?: string | null;
  button_id?: string | null;
  count: number;
  window_ms: number;
  sequence: { device_id?: string; button_id?: string }[];
  reset_on_other_input: boolean;
}

export interface IRAutomation {
  id?: string | null;
  name: string;
  enabled: boolean;
  allow_parallel: boolean;
  triggers: IRAutomationTrigger[];
  ha_expose_button: boolean;
  actions: IRAutomationAction[];
  ordering?: number;
}

export interface BridgeSettings {
  echo_enabled: boolean;
  echo_timeout: number;
  echo_smart: boolean;
  echo_ignore_self: boolean;
  echo_ignore_others: boolean;
}

export interface ReceivedCode {
  protocol: string;
  payload: IRCodePayload;
  receiver_id?: string;
  channel?: string | string[];
  timestamp: number;
  ignored?: boolean;
}

export interface ReceiverConfig {
  id: string;
}

export interface TransmitterConfig {
  id: string;
}

export interface Bridge {
  id: string;
  name: string;
  status: 'online' | 'offline' | 'connecting';
  connection_type?: 'mqtt' | 'serial';
  network_type?: 'wifi' | 'ethernet';
  ip?: string;
  serial_port?: string;
  mac?: string;
  version?: string;
  capabilities?: string[];
  receivers?: ReceiverConfig[];
  transmitters?: TransmitterConfig[];
  enabled_protocols?: string[];
  last_seen?: string;
  last_received?: ReceivedCode[];
  last_sent?: ReceivedCode[];
  settings?: BridgeSettings;
}
