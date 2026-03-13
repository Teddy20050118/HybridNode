import React, { useMemo, useState } from 'react';
import styled from 'styled-components';

// --- Styled Components (確保沒有 Emoji，且符合深色主題) ---
const ModalOverlay = styled.div`
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 99999;
  font-family: 'Consolas', monospace;
`;

const ModalContainer = styled.div`
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: 8px;
  width: 700px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 10px 30px rgba(0,0,0,0.5);
  color: #e0e0e0;
`;

const Header = styled.div`
  padding: 20px;
  border-bottom: 1px solid #333;
  background: #252525;
  border-radius: 8px 8px 0 0;
`;

const Title = styled.h2`
  margin: 0;
  color: #fff;
  font-size: 20px;
`;

const Subtitle = styled.div`
  color: #888;
  font-size: 14px;
  margin-top: 5px;
`;

const Content = styled.div`
  padding: 20px;
`;

const SectionTitle = styled.h3`
  font-size: 16px;
  color: #66ccff;
  border-bottom: 1px solid #333;
  padding-bottom: 5px;
  margin-top: 25px;
  margin-bottom: 15px;
`;

const InputRow = styled.div`
  display: flex;
  align-items: center;
  margin-bottom: 15px;
  background: #2a2a2a;
  padding: 10px;
  border-radius: 4px;
`;

const Label = styled.div`
  width: 120px;
  font-weight: bold;
  color: #ccc;
`;

const StyledInput = styled.input`
  background: #111;
  border: 1px solid #444;
  color: #fff;
  padding: 6px 10px;
  border-radius: 4px;
  flex: 1;
  margin-right: 10px;
  font-family: inherit;
  &:focus { outline: none; border-color: #66ccff; }
`;

const StyledSelect = styled.select`
  background: #111;
  border: 1px solid #444;
  color: #fff;
  padding: 6px 10px;
  border-radius: 4px;
  width: 100px;
  font-family: inherit;
  &:focus { outline: none; border-color: #66ccff; }
`;

const ButtonContainer = styled.div`
  padding: 20px;
  border-top: 1px solid #333;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  background: #252525;
  border-radius: 0 0 8px 8px;
`;

const Button = styled.button`
  background: ${props => props.primary ? '#1f6feb' : '#333'};
  color: white;
  border: 1px solid ${props => props.primary ? '#1f6feb' : '#555'};
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: bold;
  transition: all 0.2s;
  
  &:hover {
    background: ${props => props.primary ? '#388bfd' : '#444'};
  }
`;

// --- Main Component ---
const Helper = styled.div`
  color: #999;
  font-size: 12px;
  margin-top: 4px;
`;

const ErrorText = styled.div`
  color: #ff6b6b;
  font-size: 13px;
  margin-top: 10px;
`;

const StepBox = styled.div`
  border: 1px solid #333;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 14px;
  background: #232323;
`;

const TextArea = styled.textarea`
  background: #111;
  border: 1px solid #444;
  color: #fff;
  padding: 8px 10px;
  border-radius: 4px;
  width: 100%;
  min-height: 90px;
  resize: vertical;
  font-family: inherit;
  &:focus { outline: none; border-color: #66ccff; }
`;

const Checkbox = styled.input`
  margin-right: 8px;
`;

const SmallButton = styled.button`
  background: #30363d;
  color: #fff;
  border: 1px solid #444;
  padding: 6px 10px;
  border-radius: 5px;
  cursor: pointer;
  font-family: inherit;
`;

const StimulusConfigModal = ({
  isOpen,
  onClose,
  hardwareContext,
  bridge,
  onAnalyze,
  onImportVerilog,
  isImportingVerilog
}) => {
  const [functionalDescription, setFunctionalDescription] = useState('');
  const [selectedInputs, setSelectedInputs] = useState({});
  const [selectedOutputs, setSelectedOutputs] = useState({});
  const [inputBindings, setInputBindings] = useState({});
  const [outputBindings, setOutputBindings] = useState({});
  const [testbenchPath, setTestbenchPath] = useState('');
  const [localError, setLocalError] = useState('');

  const topModule = useMemo(() => {
    return hardwareContext?.hierarchy?.top_module || '';
  }, [hardwareContext]);

  const ports = useMemo(() => {
    if (!topModule || !hardwareContext?.module_ports) {
      return { inputs: [], outputs: [] };
    }
    return hardwareContext.module_ports[topModule] || { inputs: [], outputs: [] };
  }, [hardwareContext, topModule]);

  if (!isOpen) return null;

  const toggleSelection = (kind, name) => {
    if (kind === 'input') {
      setSelectedInputs(prev => ({ ...prev, [name]: !prev[name] }));
    } else {
      setSelectedOutputs(prev => ({ ...prev, [name]: !prev[name] }));
    }
  };

  const updateBinding = (kind, name, field, value) => {
    if (kind === 'input') {
      setInputBindings(prev => ({
        ...prev,
        [name]: { ...(prev[name] || {}), [field]: value }
      }));
    } else {
      setOutputBindings(prev => ({
        ...prev,
        [name]: { ...(prev[name] || {}), [field]: value }
      }));
    }
  };

  const importVerilog = async () => {
    if (!onImportVerilog) {
      setLocalError('Verilog import handler is not available.');
      return;
    }
    setLocalError('');
    const ok = await onImportVerilog();
    if (!ok) {
      setLocalError('Verilog import failed. Please check parser logs.');
    }
  };

  const selectIndependentDataFile = (kind, name) => {
    if (!bridge?.open_data_file_dialog) {
      setLocalError('Bridge is not ready for data-file selection.');
      return;
    }

    bridge.open_data_file_dialog((resultStr) => {
      try {
        const res = JSON.parse(resultStr);
        if (res.success && res.file_path) {
          if (kind === 'input') {
            updateBinding('input', name, 'data_file', res.file_path);
          } else {
            updateBinding('output', name, 'expected_data_file', res.file_path);
          }
        }
      } catch (err) {
        setLocalError(`Failed to parse data file dialog result: ${err.message}`);
      }
    });
  };

  const selectTestbench = () => {
    if (!bridge?.open_testbench_file_dialog) {
      setLocalError('Bridge is not ready for testbench selection.');
      return;
    }

    bridge.open_testbench_file_dialog((resultStr) => {
      try {
        const res = JSON.parse(resultStr);
        if (res.success && res.file_path) {
          setTestbenchPath(res.file_path);
          setLocalError('');
        }
      } catch (err) {
        setLocalError(`Failed to parse testbench dialog result: ${err.message}`);
      }
    });
  };

  const handleSubmit = () => {
    setLocalError('');

    if (!functionalDescription.trim()) {
      setLocalError('Please provide a circuit functional description first.');
      return;
    }
    if (!testbenchPath) {
      setLocalError('Please select a testbench file before analysis.');
      return;
    }

    const selectedInputList = ports.inputs
      .filter(i => selectedInputs[i.name])
      .map(i => i.name);
    const selectedOutputList = ports.outputs
      .filter(o => selectedOutputs[o.name])
      .map(o => o.name);

    if (selectedInputList.length === 0 && selectedOutputList.length === 0) {
      setLocalError('Please select at least one input or output signal.');
      return;
    }

    const payload = {
      functional_description: functionalDescription,
      verilog_file: hardwareContext?.verilog_path || '',
      top_module: topModule,
      testbench_file: testbenchPath,
      selected_inputs: selectedInputList,
      selected_outputs: selectedOutputList,
      input_bindings: ports.inputs
        .filter(i => selectedInputs[i.name])
        .map(i => ({
          input_name: i.name,
          width: i.width,
          data_file: inputBindings[i.name]?.data_file || '',
          radix: inputBindings[i.name]?.radix || (i.width > 1 ? 'hex' : 'bin')
        })),
      output_bindings: ports.outputs
        .filter(o => selectedOutputs[o.name])
        .map(o => ({
          output_name: o.name,
          width: o.width,
          expected_data_file: outputBindings[o.name]?.expected_data_file || '',
          radix: outputBindings[o.name]?.radix || (o.width > 1 ? 'hex' : 'bin')
        }))
    };

    onAnalyze(payload);
  };

  return (
    <ModalOverlay>
      <ModalContainer>
        <Header>
          <Title>Hardware Validation Workflow</Title>
          <Subtitle>Top module: {topModule || 'N/A'}</Subtitle>
        </Header>
        
        <Content>
          <SectionTitle>Step 1: Circuit Functional Description</SectionTitle>
          <StepBox>
            <TextArea
              placeholder="Describe the intended circuit behavior and validation expectation."
              value={functionalDescription}
              onChange={(e) => setFunctionalDescription(e.target.value)}
            />
          </StepBox>

          <SectionTitle>Step 2: Upload .v File (File Import)</SectionTitle>
          <StepBox>
            <InputRow>
              <Label>Verilog (.v)</Label>
              <StyledInput
                value={hardwareContext?.verilog_path || ''}
                readOnly
                placeholder="Upload Verilog source"
              />
              <SmallButton onClick={importVerilog} disabled={!!isImportingVerilog}>
                {isImportingVerilog ? 'Importing...' : 'Upload'}
              </SmallButton>
            </InputRow>
            <Helper>After upload, the system automatically detects top-module I/O and enables module expansion.</Helper>
          </StepBox>

          <SectionTitle>Step 3: Auto-Detected Main Module I/O</SectionTitle>
          <StepBox>
            {ports.inputs.length === 0 && ports.outputs.length === 0 && (
              <Helper>No detected ports. Import a Verilog file first.</Helper>
            )}

            {ports.inputs.length > 0 && <div style={{ marginBottom: '10px', fontWeight: 'bold' }}>Inputs</div>}
            {ports.inputs.map((i) => (
              <InputRow key={`in-${i.name}`}>
                <Label>
                  <Checkbox
                    type="checkbox"
                    checked={!!selectedInputs[i.name]}
                    onChange={() => toggleSelection('input', i.name)}
                  />
                  {i.name} [{i.width}-bit]
                </Label>
              </InputRow>
            ))}

            {ports.outputs.length > 0 && <div style={{ marginBottom: '10px', marginTop: '12px', fontWeight: 'bold' }}>Outputs</div>}
            {ports.outputs.map((o) => (
              <InputRow key={`out-${o.name}`}>
                <Label>
                  <Checkbox
                    type="checkbox"
                    checked={!!selectedOutputs[o.name]}
                    onChange={() => toggleSelection('output', o.name)}
                  />
                  {o.name} [{o.width}-bit]
                </Label>
              </InputRow>
            ))}
          </StepBox>

          <SectionTitle>Step 4: Independent .dat Upload Per Selected I/O</SectionTitle>
          <StepBox>
            {ports.inputs.filter(i => selectedInputs[i.name]).map((i) => (
              <InputRow key={`bind-in-${i.name}`}>
                <Label>{i.name}</Label>
                <StyledInput
                  value={inputBindings[i.name]?.data_file || ''}
                  readOnly
                  placeholder="Upload this input's .dat file"
                />
                <SmallButton onClick={() => selectIndependentDataFile('input', i.name)}>Upload</SmallButton>
                <StyledSelect
                  value={inputBindings[i.name]?.radix || (i.width > 1 ? 'hex' : 'bin')}
                  onChange={(e) => updateBinding('input', i.name, 'radix', e.target.value)}
                >
                  <option value="bin">bin</option>
                  <option value="hex">hex</option>
                  <option value="dec">dec</option>
                </StyledSelect>
              </InputRow>
            ))}

            {ports.outputs.filter(o => selectedOutputs[o.name]).map((o) => (
              <InputRow key={`bind-out-${o.name}`}>
                <Label>{o.name}</Label>
                <StyledInput
                  value={outputBindings[o.name]?.expected_data_file || ''}
                  readOnly
                  placeholder="Upload this output's expected .dat file"
                />
                <SmallButton onClick={() => selectIndependentDataFile('output', o.name)}>Upload</SmallButton>
                <StyledSelect
                  value={outputBindings[o.name]?.radix || (o.width > 1 ? 'hex' : 'bin')}
                  onChange={(e) => updateBinding('output', o.name, 'radix', e.target.value)}
                >
                  <option value="bin">bin</option>
                  <option value="hex">hex</option>
                  <option value="dec">dec</option>
                </StyledSelect>
              </InputRow>
            ))}
          </StepBox>

          <SectionTitle>Step 5: Independent Testbench Upload</SectionTitle>
          <StepBox>
            <InputRow>
              <Label>Testbench</Label>
              <StyledInput value={testbenchPath} readOnly placeholder="Select a testbench file" />
              <SmallButton onClick={selectTestbench}>Browse</SmallButton>
            </InputRow>
            <Helper>User-provided testbench is required. No rigid auto-generated testbench is used in this flow.</Helper>
          </StepBox>

          {localError && <ErrorText>{localError}</ErrorText>}
        </Content>

        <ButtonContainer>
          <Button onClick={onClose}>Cancel</Button>
          <Button primary onClick={handleSubmit}>Run Analysis</Button>
        </ButtonContainer>
      </ModalContainer>
    </ModalOverlay>
  );
};

export default StimulusConfigModal;